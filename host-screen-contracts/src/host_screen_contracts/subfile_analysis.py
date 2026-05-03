from __future__ import annotations

import re
from typing import Any

from .config import DEFAULT_CONFIG, ExtractionConfig
from .field_classification import detect_subfile_like
from .trace_schema import ScreenEvent


PAGING_TOKENS = ("PAGEUP", "PAGEDOWN", "MORE", "BOTTOM", "F7", "F8")


def _row_pattern(row: str) -> str:
    pattern = re.sub(r"[A-Za-z0-9]+", "X", row.rstrip())
    return re.sub(r"\s+", " ", pattern).strip()


def analyze_subfile_regions(screen: ScreenEvent, config: ExtractionConfig = DEFAULT_CONFIG) -> list[dict[str, Any]]:
    if not detect_subfile_like(screen, config):
        return []

    patterned_rows: dict[str, list[int]] = {}
    for row_number, row_text in enumerate(screen.text, start=1):
        pattern = _row_pattern(row_text)
        if not pattern:
            continue
        patterned_rows.setdefault(pattern, []).append(row_number)

    repeated = [
        rows
        for rows in patterned_rows.values()
        if len(rows) >= config.detect_subfile_min_repeated_rows
    ]
    repeated_rows = max(repeated, key=len) if repeated else []
    option_columns = sorted(
        {
            field.col
            for field in screen.fields
            if not field.protected and field.length <= 3
        }
    )
    upper_text = "\n".join(screen.text).upper()
    paging_indicators = [token for token in PAGING_TOKENS if token in upper_text]
    labels = [token for token in ("OPT", "OPTION", "MORE", "BOTTOM") if token in upper_text]

    if repeated_rows:
        start_row = min(repeated_rows)
        end_row = max(repeated_rows)
    else:
        field_rows = [field.row for field in screen.fields if not field.protected]
        start_row = min(field_rows) if field_rows else None
        end_row = max(field_rows) if field_rows else None

    return [
        {
            "region_kind": "subfile_like",
            "start_row": start_row,
            "end_row": end_row,
            "option_columns": option_columns,
            "paging_indicators": paging_indicators,
            "labels": labels,
            "repeated_row_count": len(repeated_rows),
            "review_required": True,
            "reason": "Subfile/list row-selection and paging semantics require human review before wrapper design.",
        }
    ]
