"""Detection of OS junk files commonly shipped inside archives."""

from __future__ import annotations

from typing import Sequence

#: Directory names that are pure OS noise.
JUNK_DIR_NAMES = {"__MACOSX"}

#: File names that are pure OS noise.
JUNK_FILE_NAMES = {".ds_store", "thumbs.db", "desktop.ini", "ehthumbs.db"}


def is_junk(components: Sequence[str]) -> bool:
    """Return True when a path (already split into components) is OS junk.

    Covers macOS ``__MACOSX`` resource directories, AppleDouble ``._*``
    files, ``.DS_Store``, and Windows thumbnail/desktop metadata.
    """
    if not components:
        return True
    if any(part in JUNK_DIR_NAMES for part in components):
        return True
    basename = components[-1]
    if basename.lower() in JUNK_FILE_NAMES:
        return True
    if basename.startswith("._"):
        return True
    return False
