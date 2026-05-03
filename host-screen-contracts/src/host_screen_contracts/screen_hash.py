from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import ExtractionConfig, DEFAULT_CONFIG
from .field_map import FieldMap
from .trace_schema import ScreenEvent, TraceField


@dataclass(frozen=True)
class ScreenHashes:
    screen_hash: str
    normalized_text_hash: str
    field_layout_hash: str
    cursor_hash: str | None


def normalize_text(text: list[str], rows: int, cols: int) -> list[str]:
    normalized = [(row[:cols]).ljust(cols) for row in text[:rows]]
    while len(normalized) < rows:
        normalized.append(" " * cols)
    return normalized


def _blank_span(rows: list[str], row: int, col: int, length: int) -> None:
    if row < 1 or row > len(rows):
        return
    line = rows[row - 1]
    start = max(0, col - 1)
    end = min(len(line), start + length)
    rows[row - 1] = line[:start] + (" " * (end - start)) + line[end:]


def normalized_text_for_hash(
    screen: ScreenEvent,
    screen_ref: str,
    field_map: FieldMap | None = None,
) -> list[str]:
    rows = normalize_text(screen.text, screen.rows, screen.cols)
    for field in screen.fields:
        _blank_span(rows, field.row, field.col, field.length)
    if field_map:
        for entry in field_map.entries_for(screen_ref):
            if entry.row is not None and entry.col is not None and entry.length is not None:
                _blank_span(rows, entry.row, entry.col, entry.length)
        for region in field_map.volatile_for(screen_ref):
            _blank_span(rows, region.row, region.col, region.length)
    return rows


def field_layout_payload(screen: ScreenEvent, field_map: FieldMap | None = None, screen_ref: str | None = None) -> str:
    fields: list[TraceField] = list(screen.fields)
    if field_map and screen_ref:
        known = {(field.id, field.row, field.col) for field in fields}
        for entry in field_map.entries_for(screen_ref):
            if entry.row is None or entry.col is None or entry.length is None:
                continue
            synthetic_id = entry.field_id or f"f_{entry.row:02d}_{entry.col:02d}"
            key = (synthetic_id, entry.row, entry.col)
            if key not in known:
                fields.append(
                    TraceField(
                        id=synthetic_id,
                        row=entry.row,
                        col=entry.col,
                        length=entry.length,
                        value="",
                        protected=entry.role not in ("input", "input_output"),
                        display_only=entry.role == "output",
                        hidden=entry.role == "hidden",
                        attributes=[],
                    )
                )
    parts = []
    for field in sorted(fields, key=lambda f: (f.row, f.col, f.id or "")):
        parts.append(
            "|".join(
                [
                    field.id or "",
                    str(field.row),
                    str(field.col),
                    str(field.length),
                    "P" if field.protected else "U",
                    "D" if field.display_only else "I",
                    "H" if field.hidden else "V",
                    ",".join(sorted(field.attributes)),
                ]
            )
        )
    return "\n".join(parts)


def _sha(payload: str, length: int) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def compute_screen_hashes(
    screen: ScreenEvent,
    screen_ref: str,
    field_map: FieldMap | None = None,
    config: ExtractionConfig = DEFAULT_CONFIG,
) -> ScreenHashes:
    normalized_rows = normalized_text_for_hash(screen, screen_ref, field_map)
    normalized_payload = "\n".join(normalized_rows)
    layout_payload = field_layout_payload(screen, field_map, screen_ref)
    cursor_payload = None
    if screen.cursor:
        cursor_payload = f"{screen.cursor.row}:{screen.cursor.col}"
    return ScreenHashes(
        screen_hash=_sha(normalized_payload + "\n---layout---\n" + layout_payload, config.generated_hash_length),
        normalized_text_hash=_sha(normalized_payload, config.generated_hash_length),
        field_layout_hash=_sha(layout_payload, config.generated_hash_length),
        cursor_hash=_sha(cursor_payload, config.generated_hash_length) if cursor_payload else None,
    )
