from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .models import DfFilesystem


_HUMAN_SIZE_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)?)(?P<unit>[KMGTPE]?)(?:i?B?)?$", re.I)


def _parse_percent(value: str) -> Optional[float]:
    value = value.strip()
    if value.endswith("%"):
        value = value[:-1]
    try:
        return float(value)
    except ValueError:
        return None


def _parse_human_size(value: str) -> Optional[int]:
    value = value.strip()
    if not value or value == "-":
        return None
    if value.isdigit():
        return int(value)
    match = _HUMAN_SIZE_RE.match(value)
    if not match:
        return None
    number = float(match.group("num"))
    unit = match.group("unit").upper()
    powers = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}
    return int(number * (1024 ** powers[unit]))


def _block_multiplier(header: str) -> int | None:
    normalized = header.lower()
    if "1b-block" in normalized:
        return 1
    if "1024-block" in normalized or "1k-block" in normalized:
        return 1024
    if "512-block" in normalized:
        return 512
    return None


def parse_df_text(text: str) -> tuple[list[DfFilesystem], list[str]]:
    entries: list[DfFilesystem] = []
    warnings: list[str] = []
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return entries, ["DF_EMPTY"]

    header_seen = False
    has_type = False
    multiplier: int | None = None
    human_sizes = True

    for line in lines:
        if line.lower().startswith("filesystem"):
            header_seen = True
            tokens = line.split()
            has_type = "Type" in tokens
            size_header = next((token for token in tokens if "blocks" in token.lower()), "Size")
            multiplier = _block_multiplier(size_header)
            human_sizes = multiplier is None
            continue

        parts = line.split()
        minimum = 7 if has_type else 6
        if len(parts) < minimum:
            warnings.append(f"DF_UNPARSED_LINE:{line}")
            continue

        try:
            if has_type:
                filesystem = parts[0]
                fs_type = parts[1]
                size_s, used_s, avail_s, pct_s = parts[2:6]
                mount_path = " ".join(parts[6:])
            else:
                filesystem = parts[0]
                fs_type = None
                size_s, used_s, avail_s, pct_s = parts[1:5]
                mount_path = " ".join(parts[5:])

            if human_sizes:
                size_bytes = _parse_human_size(size_s)
                used_bytes = _parse_human_size(used_s)
                avail_bytes = _parse_human_size(avail_s)
            else:
                size_bytes = int(float(size_s)) * int(multiplier or 1)
                used_bytes = int(float(used_s)) * int(multiplier or 1)
                avail_bytes = int(float(avail_s)) * int(multiplier or 1)

            entries.append(
                DfFilesystem(
                    filesystem=filesystem,
                    fs_type=fs_type,
                    size_bytes=size_bytes,
                    used_bytes=used_bytes,
                    available_bytes=avail_bytes,
                    capacity_pct=_parse_percent(pct_s),
                    mount_path=mount_path,
                    raw=line,
                )
            )
        except (ValueError, IndexError) as exc:
            warnings.append(f"DF_UNPARSED_LINE:{line}:{exc}")

    if not header_seen:
        warnings.append("DF_HEADER_MISSING")
    if not entries:
        warnings.append("DF_NO_FILESYSTEMS_PARSED")
    return entries, warnings


def parse_df_file(path: Path) -> tuple[list[DfFilesystem], list[str]]:
    return parse_df_text(path.read_text(encoding="utf-8", errors="replace"))

