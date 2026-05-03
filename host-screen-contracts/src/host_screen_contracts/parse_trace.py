from __future__ import annotations

import json
from pathlib import Path

from .trace_schema import ActionEvent, NoteEvent, ScreenEvent, TraceEvent, parse_event


class TraceParseError(ValueError):
    pass


def load_trace(path: str | Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    trace_path = Path(path)
    for line_number, raw_line in enumerate(trace_path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            events.append(parse_event(data))
        except Exception as exc:  # noqa: BLE001 - include line number for CLI users
            raise TraceParseError(f"{trace_path}:{line_number}: {exc}") from exc
    return events


def screen_events(events: list[TraceEvent]) -> list[ScreenEvent]:
    return [event for event in events if isinstance(event, ScreenEvent)]


def action_events(events: list[TraceEvent]) -> list[ActionEvent]:
    return [event for event in events if isinstance(event, ActionEvent)]


def note_events(events: list[TraceEvent]) -> list[NoteEvent]:
    return [event for event in events if isinstance(event, NoteEvent)]
