from __future__ import annotations

import re
from pathlib import Path

from .models import MountEntry


_MOUNT_RE = re.compile(
    r"^(?P<source>.+?) on (?P<mount_path>.+?) type (?P<fs_type>\S+) \((?P<options>.*)\)$"
)


def parse_mount_text(text: str) -> tuple[list[MountEntry], list[str]]:
    entries: list[MountEntry] = []
    warnings: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _MOUNT_RE.match(line)
        if not match:
            warnings.append(f"MOUNT_UNPARSED_LINE:{line}")
            continue
        entries.append(
            MountEntry(
                source=match.group("source"),
                mount_path=match.group("mount_path"),
                fs_type=match.group("fs_type"),
                options=[part.strip() for part in match.group("options").split(",") if part.strip()],
                raw=line,
            )
        )
    if not entries:
        warnings.append("MOUNT_NO_ENTRIES_PARSED")
    return entries, warnings


def parse_mount_file(path: Path) -> tuple[list[MountEntry], list[str]]:
    return parse_mount_text(path.read_text(encoding="utf-8", errors="replace"))

