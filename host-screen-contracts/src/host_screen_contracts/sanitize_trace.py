from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .field_classification import find_field
from .field_map import FieldMap
from .models import screen_ref_for_seq
from .privacy_report import LIKELY_SENSITIVE_TEXT_RE, _non_sensitive_spans, _overlaps, generate_privacy_report
from .redact import REDACTED, should_redact
from .tokenize import stable_token
from .trace_schema import ActionEvent, ScreenEvent, TraceEvent, parse_event


def _replacement(value: str, *, tokenize: bool, salt: str) -> str:
    if value == "":
        return value
    return stable_token(value, salt=salt, prefix="REDACTED") if tokenize else REDACTED


def _replace_span(row: str, col: int, length: int, value: str) -> str:
    if col < 1 or length < 1:
        return row
    start = col - 1
    padded = row.ljust(start + length)
    replacement = value[:length].ljust(length)
    return padded[:start] + replacement + padded[start + length :]


def _redact_text_patterns(row: str, *, tokenize: bool, salt: str, non_sensitive_spans: list[tuple[int, int]] | None = None) -> str:
    pieces: list[str] = []
    last = 0
    non_sensitive_spans = non_sensitive_spans or []
    for match in LIKELY_SENSITIVE_TEXT_RE.finditer(row):
        if _overlaps(non_sensitive_spans, match.start() + 1, match.end()):
            continue
        pieces.append(row[last : match.start()])
        value = _replacement(match.group(0), tokenize=tokenize, salt=salt)
        pieces.append(value[: len(match.group(0))].ljust(len(match.group(0))))
        last = match.end()
    pieces.append(row[last:])
    return "".join(pieces)


def _sanitize_event_dict(
    event_dict: dict[str, Any],
    *,
    screen_ref: str | None,
    screen: ScreenEvent | None,
    field_map: FieldMap,
    tokenize: bool,
    salt: str,
) -> dict[str, Any]:
    event = parse_event(event_dict)
    if isinstance(event, ScreenEvent):
        current_ref = screen_ref_for_seq(event.seq)
        sanitized = event.model_dump(mode="json", exclude_none=True)
        text = list(sanitized.get("text", []))
        non_sensitive_spans = _non_sensitive_spans(event, current_ref, field_map)
        for field_dict, field in zip(sanitized.get("fields", []), event.fields, strict=False):
            entry = field_map.find_for_field(current_ref, field)
            name = entry.name if entry and entry.name else field.id
            redact_field = field.hidden or should_redact(name, entry, redact=True)
            if redact_field:
                original_value = str(field_dict.get("value", ""))
                replacement = _replacement(original_value, tokenize=tokenize, salt=salt)
                field_dict["value"] = replacement
                if 1 <= field.row <= len(text):
                    text[field.row - 1] = _replace_span(text[field.row - 1], field.col, field.length, replacement)
        for entry in field_map.entries_for(current_ref):
            if entry.row is None or entry.col is None or entry.length is None:
                continue
            name = entry.name or entry.field_id
            redact_entry = entry.role == "hidden" or should_redact(name, entry, redact=True)
            if redact_entry and 1 <= entry.row <= len(text):
                span = text[entry.row - 1].ljust(entry.col - 1 + entry.length)[entry.col - 1 : entry.col - 1 + entry.length]
                replacement = _replacement(span.strip(), tokenize=tokenize, salt=salt)
                text[entry.row - 1] = _replace_span(text[entry.row - 1], entry.col, entry.length, replacement)
        sanitized["text"] = [
            _redact_text_patterns(row, tokenize=tokenize, salt=salt, non_sensitive_spans=non_sensitive_spans.get(row_number, []))
            for row_number, row in enumerate(text, start=1)
        ]
        return sanitized
    if isinstance(event, ActionEvent):
        sanitized = event.model_dump(mode="json", exclude_none=True)
        for input_dict, action_input in zip(sanitized.get("inputs", []), event.inputs, strict=False):
            entry = None
            name = action_input.field_id
            if screen_ref and screen:
                field = find_field(
                    screen_ref,
                    screen,
                    field_map,
                    field_id=action_input.field_id,
                    row=action_input.row,
                    col=action_input.col,
                    fallback_value=action_input.value,
                )
                if field is not None:
                    entry = field_map.find_for_field(screen_ref, field)
                    name = entry.name if entry and entry.name else field.id
            if should_redact(name, entry, redact=True):
                input_dict["value"] = _replacement(str(input_dict.get("value", "")), tokenize=tokenize, salt=salt)
        return sanitized
    return event.model_dump(mode="json", exclude_none=True)


def sanitize_trace_events(
    events: list[TraceEvent],
    *,
    field_map: FieldMap | None = None,
    tokenize: bool = False,
    salt: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    field_map = field_map or FieldMap()
    sanitized: list[dict[str, Any]] = []
    latest_screen: tuple[str, ScreenEvent] | None = None
    for event in events:
        event_dict = event.model_dump(mode="json", exclude_none=True)
        screen_ref, screen = latest_screen if latest_screen else (None, None)
        sanitized_dict = _sanitize_event_dict(
            event_dict,
            screen_ref=screen_ref,
            screen=screen,
            field_map=field_map,
            tokenize=tokenize,
            salt=salt,
        )
        sanitized.append(sanitized_dict)
        parsed_sanitized = parse_event(sanitized_dict)
        if isinstance(parsed_sanitized, ScreenEvent):
            latest_screen = (screen_ref_for_seq(parsed_sanitized.seq), parsed_sanitized)
    sanitized_events = [parse_event(item) for item in sanitized]
    report = generate_privacy_report(sanitized_events, field_map)
    return sanitized, report


def write_sanitized_trace(path: str | Path, events: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n")
