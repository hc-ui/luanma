"""Read, preview, extract and rewrite zip archives with mojibake names."""

from __future__ import annotations

import os
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .detect import DetectionResult, detect_names
from .junk import is_junk
from .sanitize import safe_components

#: General-purpose bit 11: filename is UTF-8.
UTF8_FLAG = 0x800

#: General-purpose bit 0: entry is encrypted.
ENCRYPTED_FLAG = 0x1


class ArchiveError(Exception):
    """Raised when an archive cannot be opened or processed."""


def _fs_path(p: Path) -> str:
    """Filesystem path string, with Windows long-path prefix when needed.

    Classic Windows APIs cap paths at 260 characters; deep directory trees
    with CJK names hit that easily. The ``\\\\?\\`` prefix lifts the limit.
    """
    s = str(p)
    if os.name == "nt" and len(s) >= 248 and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(s)
    return s


@dataclass
class EntryPreview:
    """One archive member, before and after the name fix."""

    original: str  # name as naive tools display it (mojibake)
    fixed: str  # name decoded with the chosen encoding
    is_dir: bool
    is_junk: bool
    flagged_utf8: bool  # True when the entry already carried the UTF-8 flag

    @property
    def needs_fix(self) -> bool:
        return self.fixed != self.original

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "fixed": self.fixed,
            "dir": self.is_dir,
            "junk": self.is_junk,
            "utf8_flagged": self.flagged_utf8,
        }


@dataclass
class ExtractReport:
    dest: str
    encoding: Optional[str]
    extracted: int = 0
    junk_skipped: int = 0
    renamed: int = 0
    sanitized: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dest": self.dest,
            "encoding": self.encoding,
            "extracted": self.extracted,
            "junk_skipped": self.junk_skipped,
            "renamed": self.renamed,
            "sanitized": self.sanitized,
            "errors": self.errors,
        }


@dataclass
class ConvertReport:
    output: str
    encoding: Optional[str]
    converted: int = 0
    junk_skipped: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "output": self.output,
            "encoding": self.encoding,
            "converted": self.converted,
            "junk_skipped": self.junk_skipped,
            "errors": self.errors,
        }


def _open(path) -> zipfile.ZipFile:
    p = Path(path)
    if not p.is_file():
        raise ArchiveError(f"文件不存在: {p}")
    try:
        return zipfile.ZipFile(p)
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"不是有效的 zip 文件: {p} ({exc})") from exc


def _is_flagged(info: zipfile.ZipInfo) -> bool:
    return bool(info.flag_bits & UTF8_FLAG)


def _raw_name(info: zipfile.ZipInfo) -> bytes:
    """Original name bytes as stored in the archive.

    Python decodes unflagged names with cp437, which maps every byte, so
    re-encoding recovers the exact bytes.
    """
    if _is_flagged(info):
        return info.filename.encode("utf-8")
    return info.filename.encode("cp437")


def _decode_name(info: zipfile.ZipInfo, encoding: Optional[str]) -> str:
    if _is_flagged(info) or encoding is None:
        return info.filename
    return _raw_name(info).decode(encoding, errors="replace")


def detect_zip(path) -> DetectionResult:
    """Detect the filename encoding used by a zip archive."""
    with _open(path) as zf:
        raws = [_raw_name(i) for i in zf.infolist() if not _is_flagged(i)]
    return detect_names(raws)


def _resolve_encoding(
    zf: zipfile.ZipFile, encoding: Optional[str]
) -> Tuple[DetectionResult, Optional[str]]:
    if encoding is not None:
        "".encode(encoding)  # validate early; raises LookupError if unknown
        det = DetectionResult(encoding, "forced", True)
        return det, encoding
    raws = [_raw_name(i) for i in zf.infolist() if not _is_flagged(i)]
    det = detect_names(raws)
    return det, det.encoding if det.needs_fix else None


def _previews(
    zf: zipfile.ZipFile, encoding: Optional[str]
) -> List[EntryPreview]:
    previews = []
    for info in zf.infolist():
        fixed = _decode_name(info, encoding)
        components, _ = safe_components(fixed)
        previews.append(
            EntryPreview(
                original=info.filename,
                fixed="/".join(components) + ("/" if info.is_dir() else ""),
                is_dir=info.is_dir(),
                is_junk=is_junk(components),
                flagged_utf8=_is_flagged(info),
            )
        )
    return previews


def preview_zip(
    path, encoding: Optional[str] = None
) -> Tuple[DetectionResult, List[EntryPreview]]:
    """Detect encoding and return the before/after name table. Reads only."""
    with _open(path) as zf:
        det, enc = _resolve_encoding(zf, encoding)
        return det, _previews(zf, enc)


def _unique_path(target: Path) -> Tuple[Path, bool]:
    """Return a collision-free path, appending `` (2)``, `` (3)``, ..."""
    if not os.path.exists(_fs_path(target)):
        return target, False
    stem, suffix = target.stem, target.suffix
    n = 2
    while True:
        candidate = target.with_name(f"{stem} ({n}){suffix}")
        if not os.path.exists(_fs_path(candidate)):
            return candidate, True
        n += 1


def _set_mtime(target: Path, info: zipfile.ZipInfo) -> None:
    try:
        stamp = time.mktime(info.date_time + (0, 0, -1))
        os.utime(_fs_path(target), (stamp, stamp))
    except (OverflowError, ValueError, OSError):
        pass  # bogus timestamps in the archive are not worth failing over


def extract_zip(
    path,
    dest=None,
    encoding: Optional[str] = None,
    keep_junk: bool = False,
    password: Optional[str] = None,
) -> ExtractReport:
    """Extract an archive using the detected (or given) filename encoding.

    Never touches the source archive. Protects against zip-slip, sanitizes
    Windows-illegal names, skips OS junk files unless ``keep_junk``.
    ``password`` unlocks ZipCrypto-encrypted entries.
    """
    src = Path(path)
    dest_dir = Path(dest) if dest is not None else src.parent / src.stem
    pwd = password.encode("utf-8") if password else None
    with _open(src) as zf:
        det, enc = _resolve_encoding(zf, encoding)
        report = ExtractReport(dest=str(dest_dir), encoding=enc)
        dest_root = dest_dir.resolve()
        os.makedirs(_fs_path(dest_dir), exist_ok=True)

        for info in zf.infolist():
            fixed = _decode_name(info, enc)
            components, changed = safe_components(fixed)
            if not components:
                continue
            if changed:
                report.sanitized += 1
            if not keep_junk and is_junk(components):
                report.junk_skipped += 1
                continue
            if info.flag_bits & ENCRYPTED_FLAG and pwd is None:
                report.errors.append(f"{fixed}: 已加密, 请用 -p 提供密码")
                continue

            target = dest_dir.joinpath(*components)
            # Belt and suspenders: sanitize already removed "..", but make
            # sure nothing can escape the destination directory.
            resolved = target.resolve()
            if resolved != dest_root and dest_root not in resolved.parents:
                report.errors.append(f"跳过越界路径: {fixed}")
                continue

            try:
                if info.is_dir():
                    os.makedirs(_fs_path(target), exist_ok=True)
                    continue
                os.makedirs(_fs_path(target.parent), exist_ok=True)
                target, renamed = _unique_path(target)
                if renamed:
                    report.renamed += 1
                with zf.open(info, pwd=pwd) as src_f:
                    with open(_fs_path(target), "wb") as dst_f:
                        shutil.copyfileobj(src_f, dst_f)
            except (NotImplementedError, RuntimeError, OSError) as exc:
                report.errors.append(f"{fixed}: {exc}")
                continue
            _set_mtime(target, info)
            report.extracted += 1
    return report


def _dedupe_name(components, is_dir: bool, used: set) -> str:
    """Join components into a zip member name unique within ``used``."""
    suffix = "/" if is_dir else ""
    name = "/".join(components) + suffix
    if name.casefold() not in used:
        used.add(name.casefold())
        return name
    last = components[-1]
    if "." in last.lstrip("."):
        stem, _, ext = last.rpartition(".")
        ext = "." + ext
    else:
        stem, ext = last, ""
    n = 2
    while True:
        candidate_last = f"{stem} ({n}){ext}"
        name = "/".join([*components[:-1], candidate_last]) + suffix
        if name.casefold() not in used:
            used.add(name.casefold())
            return name
        n += 1


def convert_zip(
    path,
    output=None,
    encoding: Optional[str] = None,
    keep_junk: bool = False,
    password: Optional[str] = None,
) -> ConvertReport:
    """Rewrite an archive so every filename is proper UTF-8 (flag set).

    The result opens with correct names in any modern tool on any OS.
    Compression type, timestamps, permissions and the archive comment are
    preserved; OS junk files are dropped unless ``keep_junk``. Encrypted
    entries are decrypted with ``password`` and stored unencrypted (the
    standard library cannot write encrypted zips).
    """
    src = Path(path)
    out = Path(output) if output is not None else src.with_name(
        src.stem + "_utf8.zip"
    )
    if out.resolve() == src.resolve():
        raise ArchiveError("输出文件不能与源文件相同")
    pwd = password.encode("utf-8") if password else None

    with _open(src) as zf:
        det, enc = _resolve_encoding(zf, encoding)
        report = ConvertReport(output=str(out), encoding=enc)
        used_names: set = set()
        with zipfile.ZipFile(out, "w") as out_zf:
            out_zf.comment = zf.comment
            for info in zf.infolist():
                fixed = _decode_name(info, enc)
                components, _ = safe_components(fixed)
                if not components:
                    continue
                if not keep_junk and is_junk(components):
                    report.junk_skipped += 1
                    continue
                if info.flag_bits & ENCRYPTED_FLAG and pwd is None:
                    report.errors.append(f"{fixed}: 已加密, 请用 -p 提供密码")
                    continue

                name = _dedupe_name(components, info.is_dir(), used_names)

                new_info = zipfile.ZipInfo(name, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.external_attr = info.external_attr
                new_info.internal_attr = info.internal_attr
                new_info.create_system = info.create_system
                try:
                    if info.is_dir():
                        out_zf.writestr(new_info, b"")
                    else:
                        with zf.open(info, pwd=pwd) as src_f:
                            with out_zf.open(new_info, "w") as dst_f:
                                shutil.copyfileobj(src_f, dst_f)
                except (NotImplementedError, RuntimeError, OSError) as exc:
                    report.errors.append(f"{fixed}: {exc}")
                    continue
                report.converted += 1
    return report
