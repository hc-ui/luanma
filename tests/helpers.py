"""Test helpers: build zip archives with raw (non-UTF-8) filename bytes,
including ZipCrypto-encrypted archives (stdlib cannot write those).
"""

from __future__ import annotations

import struct
import zipfile
import zlib
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


# --- ZipCrypto writer (traditional PKWARE encryption) -------------------

_CRC_TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _CRC_TABLE.append(_c)


class _ZipCryptoKeys:
    def __init__(self, password: bytes):
        self.k0, self.k1, self.k2 = 0x12345678, 0x23456789, 0x34567890
        for b in password:
            self._update(b)

    @staticmethod
    def _crc32(ch: int, crc: int) -> int:
        return (crc >> 8) ^ _CRC_TABLE[(crc ^ ch) & 0xFF]

    def _update(self, b: int) -> None:
        self.k0 = self._crc32(b, self.k0)
        self.k1 = (self.k1 + (self.k0 & 0xFF)) & 0xFFFFFFFF
        self.k1 = (self.k1 * 134775813 + 1) & 0xFFFFFFFF
        self.k2 = self._crc32((self.k1 >> 24) & 0xFF, self.k2)

    def encrypt(self, plain: bytes) -> bytes:
        out = bytearray()
        for p in plain:
            t = (self.k2 | 2) & 0xFFFF
            out.append(p ^ (((t * (t ^ 1)) >> 8) & 0xFF))
            self._update(p)
        return bytes(out)


def make_encrypted_zip(
    path: Union[str, Path],
    name: str,
    data: bytes,
    password: str,
    encoding: str = "gbk",
) -> Path:
    """Create a zip with one ZipCrypto-encrypted, STORED entry whose name
    is raw bytes in ``encoding`` (no UTF-8 flag) -- the classic "encrypted
    course material from a Chinese Windows box" archive.
    """
    path = Path(path)
    raw_name = name.encode(encoding)
    crc = zlib.crc32(data) & 0xFFFFFFFF
    keys = _ZipCryptoKeys(password.encode("utf-8"))
    header = bytes([0x42] * 11) + bytes([(crc >> 24) & 0xFF])
    payload = keys.encrypt(header) + keys.encrypt(data)

    flag = 0x1  # encrypted; deliberately no UTF-8 flag
    dostime = 0
    dosdate = ((2026 - 1980) << 9) | (8 << 5) | 13
    local = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50, 20, flag, 0, dostime, dosdate,
        crc, len(payload), len(data), len(raw_name), 0,
    ) + raw_name + payload
    central = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50, 20, 20, flag, 0, dostime, dosdate,
        crc, len(payload), len(data), len(raw_name), 0, 0, 0, 0, 0, 0,
    ) + raw_name
    eocd = struct.pack(
        "<IHHHHIIH",
        0x06054B50, 0, 0, 1, 1, len(central), len(local), 0,
    )
    path.write_bytes(local + central + eocd)
    return path
