"""Command-line interface for luanma."""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .detect import CANDIDATES
from .dirutil import rename_dir
from .ziputil import ArchiveError, convert_zip, extract_zip, preview_zip

_EPILOG = """\
示例:
  luanma 下载.zip                预览修复效果(只读, 不写盘)
  luanma -x 下载.zip             解压, 文件名自动修复
  luanma -x -p 密码 加密.zip     解压 ZipCrypto 加密压缩包
  luanma --fix 下载.zip          生成文件名为 UTF-8 的新压缩包
  luanma 乱码目录/               预览已解压目录的重命名计划
  luanma --rename 乱码目录/      把目录里的乱码文件名改回来
  luanma *.zip --json            批量处理, 输出 JSON
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="luanma",
        description=(
            "压缩包/目录乱码文件名自动检测与修复。"
            "默认只预览(不写盘); -x 解压; --fix 生成 UTF-8 压缩包; "
            "--rename 修复已解压目录里的乱码文件名。"
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "archives", nargs="+", metavar="archive.zip|目录",
        help="待处理的 zip 压缩包或已解压出乱码文件名的目录",
    )
    action = parser.add_argument_group("动作(默认: 预览)")
    action.add_argument(
        "-x", "--extract", action="store_true", help="按检测到的编码解压"
    )
    action.add_argument(
        "--fix",
        action="store_true",
        help="生成文件名为 UTF-8 的新压缩包(默认命名 *_utf8.zip)",
    )
    action.add_argument(
        "--rename",
        action="store_true",
        help="重命名目录里的乱码文件名(输入为目录时)",
    )
    parser.add_argument(
        "-e",
        "--encoding",
        help=f"手动指定文件名编码(可选: {', '.join(CANDIDATES)} 等)",
    )
    parser.add_argument("-d", "--dest", help="解压目标目录(配合 -x)")
    parser.add_argument(
        "-o", "--output", help="输出压缩包路径(配合 --fix, 仅限单个输入)"
    )
    parser.add_argument(
        "-p", "--password", help="加密压缩包的密码(ZipCrypto)"
    )
    parser.add_argument(
        "--keep-junk",
        action="store_true",
        help="保留 __MACOSX、.DS_Store、Thumbs.db 等系统垃圾文件",
    )
    parser.add_argument(
        "--json", action="store_true", help="以 JSON 输出(供脚本使用)"
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"luanma {__version__}"
    )
    return parser


def _display(text: str) -> str:
    """Neutralize control characters before echoing untrusted names.

    Archive members are attacker-controlled; a name embedding ESC could
    otherwise inject terminal escape sequences into the preview.
    """
    return "".join(
        ch if ch == " " or ch.isprintable() else "·" for ch in text
    )


def _shorten(text: str, width: int = 58) -> str:
    text = _display(text)
    return text if len(text) <= width else text[: width - 1] + "…"


def _print_preview(path: str, det, previews) -> None:
    if not det.needs_fix:
        print(f"{path}: 文件名编码正常(UTF-8/ASCII), 无需修复")
        return
    print(
        f"{path}: 检测到文件名编码 {det.encoding.upper()}"
        f"(置信度: {det.confidence_label})"
    )
    if det.confidence == "low":
        ranking = ", ".join(det.ranked()[:3])
        print(f"  注意: 置信度较低, 候选编码依次为 {ranking}, 可用 -e 指定")
    junk = 0
    for p in previews:
        if p.is_junk:
            junk += 1
            continue
        if p.needs_fix:
            print(f"  {_shorten(p.original)}")
            print(f"    -> {_shorten(p.fixed)}")
    if junk:
        print(f"  (另有 {junk} 个系统垃圾文件将被跳过, --keep-junk 可保留)")
    print(
        "提示: 加 -x 按此编码解压, 或加 --fix 生成 UTF-8 压缩包; "
        "-e <编码> 可手动指定"
    )


def _run_dir(path: str, args) -> dict:
    """Preview or apply mojibake renames inside an extracted directory."""
    if args.extract or args.fix:
        raise ArchiveError(
            f"{path} 是目录; -x/--fix 仅用于压缩包, 目录请用 --rename"
        )
    entry: dict = {"path": path}
    report = rename_dir(path, encoding=args.encoding, apply=args.rename)
    entry["action"] = "rename" if args.rename else "dir-preview"
    entry["report"] = report.to_dict()
    if args.json:
        return entry

    if not report.planned and not report.skipped_unsure:
        print(f"{path}: 未发现乱码文件名, 无需修复")
        return entry
    if report.planned:
        enc = (report.encoding or "?").upper()
        verb = "已重命名" if args.rename else "计划重命名"
        print(
            f"{path}: 检测到编码 {enc}(置信度: {report.confidence_label}), "
            f"{verb} {len(report.planned)} 项"
        )
        for item in report.planned:
            print(f"  {_shorten(item.old_name)}")
            print(f"    -> {_shorten(item.new_name)}")
    else:
        print(f"{path}: 未发现可确定修复的乱码文件名")
    if report.skipped_unsure:
        print(
            f"  (另有 {report.skipped_unsure} 个名字疑似乱码但把握不足, "
            "已跳过; 可用 -e 指定编码后重试)"
        )
    for err in report.errors:
        print(f"  警告: {err}")
    if report.planned and not args.rename:
        print("提示: 确认无误后加 --rename 实际重命名")
    return entry


def _run_one(path: str, args) -> dict:
    if os.path.isdir(path):
        return _run_dir(path, args)
    if args.rename:
        raise ArchiveError(f"--rename 仅用于目录, 而 {path} 不是目录")

    entry: dict = {"path": path}
    det, previews = preview_zip(path, args.encoding)
    entry["encoding"] = det.encoding
    entry["confidence"] = det.confidence
    entry["needs_fix"] = det.needs_fix
    entry["entries"] = [p.to_dict() for p in previews]

    if args.extract:
        report = extract_zip(
            path, dest=args.dest, encoding=args.encoding,
            keep_junk=args.keep_junk, password=args.password,
        )
        entry["action"] = "extract"
        entry["report"] = report.to_dict()
        if not args.json:
            print(
                f"{path}: 已解压 {report.extracted} 个文件到 {report.dest}"
                f" (编码: {report.encoding or '原样'},"
                f" 跳过垃圾文件 {report.junk_skipped},"
                f" 重名改名 {report.renamed})"
            )
            for err in report.errors:
                print(f"  警告: {_display(err)}")
    elif args.fix:
        report = convert_zip(
            path, output=args.output, encoding=args.encoding,
            keep_junk=args.keep_junk, password=args.password,
        )
        entry["action"] = "convert"
        entry["report"] = report.to_dict()
        if not args.json:
            print(
                f"{path}: 已生成 {report.output}"
                f" (共 {report.converted} 个条目, 文件名已转为 UTF-8,"
                f" 跳过垃圾文件 {report.junk_skipped})"
            )
            for err in report.errors:
                print(f"  警告: {_display(err)}")
    else:
        entry["action"] = "preview"
        if not args.json:
            _print_preview(path, det, previews)
    return entry


def _expand_archives(patterns: List[str]) -> List[str]:
    """Expand glob patterns ourselves: PowerShell/cmd do not expand ``*``."""
    paths: List[str] = []
    for pattern in patterns:
        if any(ch in pattern for ch in "*?["):
            matches = sorted(glob.glob(pattern, recursive=True))
            if matches:
                paths.extend(matches)
            else:
                paths.append(pattern)  # keep it: reported as missing later
        else:
            paths.append(pattern)
    return paths


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
            sys.stderr.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)

    actions = [args.extract, args.fix, args.rename]
    if sum(actions) > 1:
        parser.error("-x、--fix、--rename 只能选择一个")
    if args.dest and not args.extract:
        parser.error("-d 需要配合 -x 使用")
    if args.output and not args.fix:
        parser.error("-o 需要配合 --fix 使用")
    if args.encoding:
        try:
            "".encode(args.encoding)
        except LookupError:
            parser.error(f"未知编码: {args.encoding}")

    archives = _expand_archives(args.archives)
    if args.output and len(archives) > 1:
        parser.error("-o 只能用于单个压缩包")

    results = []
    failed = False
    partial = False
    for path in archives:
        try:
            entry = _run_one(path, args)
            results.append(entry)
            if entry.get("report", {}).get("errors"):
                partial = True
        except ArchiveError as exc:
            failed = True
            if args.json:
                results.append({"path": path, "error": str(exc)})
            else:
                print(f"错误: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps({"archives": results}, ensure_ascii=False, indent=2))
    if failed:
        return 2
    return 1 if partial else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
