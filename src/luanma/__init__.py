"""luanma: fix mojibake filenames in zip archives.

压缩包乱码文件名自动检测、修复与安全解压工具。
"""

from .detect import DetectionResult, detect_names
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

__version__ = "0.2.0"

__all__ = [
    "ArchiveError",
    "ConvertReport",
    "DetectionResult",
    "EntryPreview",
    "ExtractReport",
    "convert_zip",
    "detect_names",
    "detect_zip",
    "extract_zip",
    "preview_zip",
    "__version__",
]
