"""Repair mojibake file names that are already on disk.

The other half of the real-world problem: the archive was long ago
extracted with the wrong encoding, and now a directory tree is full of
names like ``ÆÚÄ©´ó×÷Òµ``. Those names are exactly the CP437 view of the
original bytes, so the transform is: re-encode the name with cp437 to get
the original bytes back, then decode with the detected encoding.

Safety model: scanning never touches the disk; renaming happens only when
explicitly requested, bottom-up (children before parents), with collision
suffixes, and skips any name whose decoded form does not plausibly look
like real text (protects e.g. legitimate ``café.txt``, whose bytes also
happen to be cp437-encodable).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .detect import (
    CONFIDENCE_LABELS,
    MIN_NAME_SCORE,
    DetectionResult,
    _score_text,
    cp437_roundtrip,
    detect_names,
)
from .sanitize import sanitize_component
from .ziputil import ArchiveError, _fs_path, _unique_path


@dataclass
class RenameItem:
    """One planned rename: a directory entry whose name is mojibake."""

    path: str  # current full path
    old_name: str
    new_name: str
    is_dir: bool

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "old": self.old_name,
            "new": self.new_name,
            "dir": self.is_dir,
        }


@dataclass
class DirReport:
    root: str
    encoding: Optional[str]
    confidence: str
    planned: List[RenameItem] = field(default_factory=list)
    renamed: int = 0
    skipped_unsure: int = 0  # cp437-encodable but not plausibly CJK
    errors: List[str] = field(default_factory=list)
    new_root: Optional[str] = None  # set when the root itself was renamed

    @property
    def needs_fix(self) -> bool:
        return bool(self.planned)

    @property
    def confidence_label(self) -> str:
        return CONFIDENCE_LABELS.get(self.confidence, self.confidence)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "encoding": self.encoding,
            "confidence": self.confidence,
            "planned": [i.to_dict() for i in self.planned],
            "renamed": self.renamed,
            "skipped_unsure": self.skipped_unsure,
            "errors": self.errors,
            "new_root": self.new_root,
        }


def _walk_entries(root: Path) -> List[Tuple[Path, str, bool]]:
    """All directory entries, deepest first (safe rename order)."""
    entries: List[Tuple[Path, str, bool]] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        base = Path(dirpath)
        for fname in filenames:
            entries.append((base, fname, False))
        for dname in dirnames:
            entries.append((base, dname, True))
    return entries


def scan_dir(
    root, encoding: Optional[str] = None
) -> Tuple[DetectionResult, DirReport]:
    """Detect the encoding of mojibake names under *root* and plan renames.

    Read-only: nothing on disk is modified.
    """
    root = Path(root)
    if not root.is_dir():
        raise ArchiveError(f"目录不存在或不是目录: {root}")

    entries = _walk_entries(root)
    candidates = [
        (base, name, is_dir, raw)
        for base, name, is_dir in entries
        if (raw := cp437_roundtrip(name)) is not None
    ]
    # The root's own name may be mojibake too; it informs detection and,
    # if fixable, is renamed last (after everything inside it).
    root_raw = cp437_roundtrip(root.name)
    det_input = [raw for *_, raw in candidates]
    if root_raw is not None:
        det_input.append(root_raw)

    if encoding is not None:
        "".encode(encoding)  # validate early
        det = DetectionResult(encoding, "forced", bool(det_input))
        enc = encoding
    else:
        det = detect_names(det_input)
        enc = det.encoding if det.needs_fix else None

    report = DirReport(
        root=str(root), encoding=enc, confidence=det.confidence
    )
    if enc is None:
        return det, report

    taken: dict = {}  # parent dir -> casefolded names already claimed
    for base, name, is_dir, raw in candidates:
        decoded = raw.decode(enc, errors="replace")
        if _score_text(decoded, enc) < MIN_NAME_SCORE:
            report.skipped_unsure += 1
            continue
        new_name, _ = sanitize_component(decoded)
        if new_name == name:
            continue
        new_name = _claim_name(base, new_name, taken)
        report.planned.append(
            RenameItem(
                path=str(base / name),
                old_name=name,
                new_name=new_name,
                is_dir=is_dir,
            )
        )

    if root_raw is not None:
        decoded = root_raw.decode(enc, errors="replace")
        if _score_text(decoded, enc) >= MIN_NAME_SCORE:
            new_name, _ = sanitize_component(decoded)
            if new_name != root.name:
                new_name = _claim_name(root.parent, new_name, taken)
                report.planned.append(
                    RenameItem(
                        path=str(root),
                        old_name=root.name,
                        new_name=new_name,
                        is_dir=True,
                    )
                )
        else:
            report.skipped_unsure += 1
    return det, report


def _claim_name(base: Path, new_name: str, taken: dict) -> str:
    """Reserve a final name unique among planned siblings and disk."""
    names = taken.setdefault(str(base), set())
    stem, suffix = Path(new_name).stem, Path(new_name).suffix
    candidate, n = new_name, 1
    while (
        candidate.casefold() in names
        or os.path.exists(_fs_path(base / candidate))
    ):
        n += 1
        candidate = f"{stem} ({n}){suffix}"
    names.add(candidate.casefold())
    return candidate


def rename_dir(
    root, encoding: Optional[str] = None, apply: bool = False
) -> DirReport:
    """Fix mojibake names under *root*.

    With ``apply=False`` (default) only returns the plan. With
    ``apply=True`` performs the renames deepest-first and records the
    outcome in the report.
    """
    _, report = scan_dir(root, encoding)
    if not apply:
        return report

    for item in report.planned:
        old = Path(item.path)
        target = old.with_name(item.new_name)
        try:
            target, _ = _unique_path(target)
            os.rename(_fs_path(old), _fs_path(target))
        except OSError as exc:
            report.errors.append(f"{item.old_name}: {exc}")
            continue
        item.new_name = target.name
        if item.path == report.root:
            report.new_root = str(target)
        report.renamed += 1
    return report
