from __future__ import annotations

from pathlib import Path

from .models import FstabEntry


def parse_fstab_text(text: str) -> tuple[list[FstabEntry], list[str]]:
    entries: list[FstabEntry] = []
    warnings: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        line = stripped.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 4:
            warnings.append(f"FSTAB_UNPARSED_LINE:{stripped}")
            continue
        source, mount_path, fs_type, options = parts[:4]
        dump = parts[4] if len(parts) > 4 else None
        passno = parts[5] if len(parts) > 5 else None
        entries.append(
            FstabEntry(
                source=source,
                mount_path=mount_path,
                fs_type=fs_type,
                options=[part.strip() for part in options.split(",") if part.strip()],
                dump=dump,
                passno=passno,
                raw=stripped,
            )
        )
    return entries, warnings


def parse_fstab_file(path: Path) -> tuple[list[FstabEntry], list[str]]:
    return parse_fstab_text(path.read_text(encoding="utf-8", errors="replace"))

