"""Test helpers: build zip archives with raw (non-UTF-8) filename bytes."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Dict, Optional, Union


class _RawNameZipInfo(zipfile.ZipInfo):
    """ZipInfo that writes exact raw name bytes without the UTF-8 flag.

    This reproduces archives produced by legacy tools (WinRAR on Chinese
    Windows, old Java, Baidu Netdisk, ...) that store local-code-page bytes.
    Relies on the private ``_encodeFilenameFlags`` hook, which is stable
    across CPython 3.9-3.13; if it changes, these tests fail loudly.
    """

    raw_name: bytes = b""

    def _encodeFilenameFlags(self):  # noqa: N802 (stdlib naming)
        return self.raw_name, 0


def make_bad_zip(
    path: Union[str, Path],
    names: Dict[str, bytes],
    encoding: str,
    flagged_names: Optional[Dict[str, bytes]] = None,
) -> Path:
    """Create a zip whose member names are raw bytes in ``encoding``.

    ``names`` maps true (str) member names to their content. Names ending
    with ``/`` become directory entries. ``flagged_names`` are written the
    normal way (UTF-8 with flag bit 11) to simulate mixed archives.
    """
    path = Path(path)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in names.items():
            info = _RawNameZipInfo(name, date_time=(2026, 8, 13, 12, 0, 0))
            info.raw_name = name.encode(encoding)
            if name.endswith("/"):
                info.external_attr = 0o40775 << 16 | 0x10
                zf.writestr(info, b"")
            else:
                zf.writestr(info, data)
        for name, data in (flagged_names or {}).items():
            zf.writestr(name, data)
    return path


def make_utf8_zip(path: Union[str, Path], names: Dict[str, bytes]) -> Path:
    """Create a normal zip with UTF-8 flagged names."""
    path = Path(path)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in names.items():
            zf.writestr(name, data)
    return path
