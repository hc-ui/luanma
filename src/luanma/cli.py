"""Command-line interface for luanma."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from .detect import CANDIDATES
from .ziputil import ArchiveError, convert_zip, extract_zip, preview_zip


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="luanma",
        description=(
            "压缩包乱码文件名自动检测、修复与安全解压。"
            "默认只预览(不写盘); -x 解压; --fix 生成 UTF-8 压缩包。"
        ),
    )
    parser.add_argument("archives", nargs="+", metavar="archive.zip")
    action = parser.add_argument_group("动作(默认: 预览)")
    action.add_argument(
        "-x", "--extract", action="store_true", help="按检测到的编码解压"
    )
    action.add_argument(
        "--fix",
        action="store_true",
        help="生成文件名为 UTF-8 的新压缩包(默认命名 *_utf8.zip)",
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


def _shorten(text: str, width: int = 58) -> str:
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


def _run_one(path: str, args) -> dict:
    entry: dict = {"path": path}
    det, previews = preview_zip(path, args.encoding)
    entry["encoding"] = det.encoding
    entry["confidence"] = det.confidence
    entry["needs_fix"] = det.needs_fix
    entry["entries"] = [p.to_dict() for p in previews]

    if args.extract:
        report = extract_zip(
            path, dest=args.dest, encoding=args.encoding,
            keep_junk=args.keep_junk,
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
                print(f"  警告: {err}")
    elif args.fix:
        report = convert_zip(
            path, output=args.output, encoding=args.encoding,
            keep_junk=args.keep_junk,
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
                print(f"  警告: {err}")
    else:
        entry["action"] = "preview"
        if not args.json:
            _print_preview(path, det, previews)
    return entry


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
            sys.stderr.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.extract and args.fix:
        parser.error("-x 与 --fix 不能同时使用")
    if args.output and len(args.archives) > 1:
        parser.error("-o 只能用于单个压缩包")
    if args.encoding:
        try:
            "".encode(args.encoding)
        except LookupError:
            parser.error(f"未知编码: {args.encoding}")

    results = []
    failed = False
    for path in args.archives:
        try:
            results.append(_run_one(path, args))
        except ArchiveError as exc:
            failed = True
            if args.json:
                results.append({"path": path, "error": str(exc)})
            else:
                print(f"错误: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps({"archives": results}, ensure_ascii=False, indent=2))
    return 2 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
