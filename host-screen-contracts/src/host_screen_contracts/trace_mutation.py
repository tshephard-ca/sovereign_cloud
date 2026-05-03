from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import screen_ref_for_seq
from .trace_schema import ActionEvent, ScreenEvent, TraceEvent


def _replace_text(row: str, col: int, length: int, value: str) -> str:
    start = max(0, col - 1)
    padded = row.ljust(start + length)
    replacement = value[:length].ljust(length)
    return padded[:start] + replacement + padded[start + length :]


def _blank_text(row: str, col: int, length: int) -> str:
    start = max(0, col - 1)
    padded = row.ljust(start + length)
    return padded[:start] + (" " * length) + padded[start + length :]


def mutate_trace_events(
    events: list[TraceEvent],
    *,
    label_changes: list[tuple[str, str]] | None = None,
    field_moves: dict[str, tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    label_changes = label_changes or []
    field_moves = field_moves or {}
    mutated: list[dict[str, Any]] = []
    moved_coordinates: dict[str, tuple[int, int]] = {}

    for event in events:
        event_dict = deepcopy(event.model_dump(mode="json", exclude_none=True))
        if isinstance(event, ScreenEvent):
            text = list(event_dict.get("text", []))
            for old, new in label_changes:
                text = [row.replace(old, new) for row in text]
            for field_dict in event_dict.get("fields", []):
                field_id = field_dict.get("id")
                if field_id not in field_moves:
                    continue
                row_delta, col_delta = field_moves[field_id]
                old_row = int(field_dict["row"])
                old_col = int(field_dict["col"])
                length = int(field_dict["length"])
                new_row = old_row + row_delta
                new_col = old_col + col_delta
                value = str(field_dict.get("value", ""))
                if 1 <= old_row <= len(text):
                    text[old_row - 1] = _blank_text(text[old_row - 1], old_col, length)
                while len(text) < new_row:
                    text.append("")
                if value:
                    text[new_row - 1] = _replace_text(text[new_row - 1], new_col, length, value)
                field_dict["row"] = new_row
                field_dict["col"] = new_col
                moved_coordinates[field_id] = (new_row, new_col)
            event_dict["text"] = text
        elif isinstance(event, ActionEvent):
            for input_dict in event_dict.get("inputs", []):
                field_id = input_dict.get("field_id")
                if field_id in moved_coordinates:
                    input_dict["row"], input_dict["col"] = moved_coordinates[field_id]
        mutated.append(event_dict)
    return mutated


def parse_label_changes(values: list[str] | None) -> list[tuple[str, str]]:
    changes: list[tuple[str, str]] = []
    for value in values or []:
        old, sep, new = value.partition(":")
        if not sep:
            raise ValueError("label changes must use OLD:NEW")
        changes.append((old, new))
    return changes


def parse_field_moves(values: list[str] | None) -> dict[str, tuple[int, int]]:
    moves: dict[str, tuple[int, int]] = {}
    for value in values or []:
        field_id, sep, delta = value.partition(":")
        if not sep:
            raise ValueError("field moves must use FIELD_ID:+ROW,+COL")
        row_text, comma, col_text = delta.partition(",")
        if not comma:
            raise ValueError("field moves must use FIELD_ID:+ROW,+COL")
        moves[field_id] = (int(row_text), int(col_text))
    return moves
