from __future__ import annotations

import re
from dataclasses import dataclass

from .config import ExtractionConfig, DEFAULT_CONFIG
from .field_map import FieldMap
from .models import Confidence
from .screen_hash import normalize_text
from .trace_schema import ScreenEvent, TraceField


@dataclass(frozen=True)
class LabelInference:
    name: str
    label: str | None
    confidence: Confidence
    source: str


_FILLER_RE = re.compile(r"[._:]+")
_SNAKE_RE = re.compile(r"[^a-z0-9]+")


def snake_case(text: str) -> str:
    value = _SNAKE_RE.sub("_", text.strip().lower()).strip("_")
    return value or "field"


def _clean_label(raw: str) -> str:
    cleaned = _FILLER_RE.sub(" ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^(?:[A-Z]\d{0,2}=.*)$", "", cleaned)
    chunks = [chunk.strip() for chunk in re.split(r"\s{2,}", cleaned) if chunk.strip()]
    return chunks[-1] if chunks else cleaned


def _nearest_left_label(row_text: str, col: int, max_chars: int) -> str | None:
    left = row_text[max(0, col - 1 - max_chars) : max(0, col - 1)]
    label = _clean_label(left)
    if re.search(r"[A-Za-z]", label):
        return label
    return None


def infer_label(screen: ScreenEvent, field: TraceField, config: ExtractionConfig = DEFAULT_CONFIG) -> LabelInference:
    rows = normalize_text(screen.text, screen.rows, screen.cols)
    same_row = rows[field.row - 1] if field.row - 1 < len(rows) else ""
    label = _nearest_left_label(same_row, field.col, config.label_scan_left_chars)
    if label:
        return LabelInference(snake_case(label), label, Confidence.MEDIUM, "label")

    if field.row > 1:
        above = rows[field.row - 2]
        start = max(0, field.col - 1 - config.label_scan_left_chars // 2)
        end = min(len(above), field.col - 1 + max(field.length, 1))
        label = _clean_label(above[start:end])
        if re.search(r"[A-Za-z]", label):
            return LabelInference(snake_case(label), label, Confidence.MEDIUM, "label")

    return LabelInference(f"field_{field.row:02d}_{field.col:02d}", None, Confidence.LOW, "coordinate")


def _blank_title_span(row: str, col: int, length: int) -> str:
    start = max(0, col - 1)
    end = min(len(row), start + length)
    return row[:start] + (" " * (end - start)) + row[end:]


def infer_screen_title(screen: ScreenEvent, field_map: FieldMap | None = None, screen_ref: str | None = None) -> str | None:
    rows = normalize_text(screen.text, screen.rows, screen.cols)
    if field_map and screen_ref:
        for region in field_map.volatile_for(screen_ref):
            if 1 <= region.row <= len(rows):
                rows[region.row - 1] = _blank_title_span(rows[region.row - 1], region.col, region.length)
    for row in rows:
        text = row.strip()
        if not text:
            continue
        if re.search(r"\bF\d{1,2}\s*=", text):
            continue
        if len(text) <= 3:
            continue
        if text.upper() == text and re.search(r"[A-Z]", text):
            return re.sub(r"\s+", " ", text)
    return None


def detect_function_keys(screen: ScreenEvent) -> list[str]:
    keys: set[str] = set()
    payload = "\n".join(screen.text).upper()
    for key in re.findall(r"\bF([1-9]|1[0-9]|2[0-4])\s*=", payload):
        keys.add(f"F{key}")
    if re.search(r"\bENTER\b", payload):
        keys.add("ENTER")
    if "PAGEUP" in payload or "PAGE UP" in payload:
        keys.add("PAGEUP")
    if "PAGEDOWN" in payload or "PAGE DOWN" in payload:
        keys.add("PAGEDOWN")
    return sorted(keys, key=lambda value: (0, int(value[1:])) if value.startswith("F") else (1, value))


def is_function_key_footer(text: str) -> bool:
    return bool(re.search(r"\bF\d{1,2}\s*=", text.upper()))
