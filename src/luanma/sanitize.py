"""Make archive member names safe to create on the local filesystem.

Handles Windows-illegal characters, reserved device names, trailing dots
and spaces, both slash styles as separators, and path-traversal components
(zip-slip). All transforms are conservative: they only replace what would
otherwise fail or escape the extraction directory.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_ILLEGAL_RE = re.compile(r'[<>:"|?*\x00-\x1f]')

_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def sanitize_component(name: str) -> Tuple[str, bool]:
    """Sanitize one path component. Returns (safe_name, changed)."""
    original = name
    if name == "..":
        name = "_"
    name = _ILLEGAL_RE.sub("_", name)
    name = name.rstrip(". ")
    if not name:
        name = "_"
    stem = name.split(".", 1)[0]
    if stem.lower() in _RESERVED:
        name = "_" + name
    return name, name != original


def split_archive_path(name: str) -> List[str]:
    """Split an archive member name into path components.

    Both ``/`` and ``\\`` are treated as separators (old Windows tools
    wrote backslashes). Empty and ``.`` components are dropped.
    """
    parts = re.split(r"[/\\]+", name)
    return [p for p in parts if p not in ("", ".")]


def safe_components(name: str) -> Tuple[List[str], bool]:
    """Split and sanitize an archive member name.

    Returns (components, changed). ``changed`` is True when any component
    had to be altered to be safe.
    """
    changed = False
    out: List[str] = []
    for part in split_archive_path(name):
        safe, part_changed = sanitize_component(part)
        changed = changed or part_changed
        out.append(safe)
    return out, changed
