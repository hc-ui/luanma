"""luanma: fix mojibake filenames in zip archives.

压缩包乱码文件名自动检测、修复与安全解压工具。
"""

from .detect import DetectionResult, detect_names
from .dirutil import DirReport, RenameItem, rename_dir, scan_dir
from .ziputil import (
    ArchiveError,
    ConvertReport,
    EntryPreview,
    ExtractReport,
    convert_zip,
    detect_zip,
    extract_zip,
    preview_zip,
)

__version__ = "0.4.0"

__all__ = [
    "ArchiveError",
    "ConvertReport",
    "DetectionResult",
    "DirReport",
    "EntryPreview",
    "ExtractReport",
    "RenameItem",
    "convert_zip",
    "detect_names",
    "detect_zip",
    "extract_zip",
    "preview_zip",
    "rename_dir",
    "scan_dir",
    "__version__",
]
