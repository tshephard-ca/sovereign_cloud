from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ScreenFieldSnapshot:
    id: str
    row: int
    col: int
    length: int
    value: str = ""
    protected: bool = False
    display_only: bool = False
    hidden: bool = False
    attributes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScreenSnapshot:
    rows: int
    cols: int
    text: list[str]
    fields: list[ScreenFieldSnapshot] = field(default_factory=list)
    cursor_row: int | None = None
    cursor_col: int | None = None


class ScreenDriver(Protocol):
    def current_screen(self) -> ScreenSnapshot: ...

    def set_field(self, field_id: str, value: str) -> None: ...

    def send_aid(self, aid: str) -> None: ...

    def wait_for_screen_change(self) -> ScreenSnapshot: ...


class TraceWriter:
    """Write neutral JSONL traces from approved offline capture workflows."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = 1
        self._events: list[dict] = []

    def write_screen(self, snapshot: ScreenSnapshot) -> None:
        event = {
            "type": "screen",
            "seq": self._seq,
            "rows": snapshot.rows,
            "cols": snapshot.cols,
            "text": snapshot.text,
            "fields": [field.__dict__ for field in snapshot.fields],
        }
        if snapshot.cursor_row is not None and snapshot.cursor_col is not None:
            event["cursor"] = {"row": snapshot.cursor_row, "col": snapshot.cursor_col}
        self._events.append(event)
        self._seq += 1

    def write_action(self, aid: str, inputs: list[dict] | None = None) -> None:
        self._events.append({"type": "action", "seq": self._seq, "aid": aid, "inputs": inputs or []})
        self._seq += 1

    def write_note(self, note: str) -> None:
        self._events.append({"type": "note", "seq": self._seq, "note": note})
        self._seq += 1

    def close(self) -> None:
        self.path.write_text("\n".join(json.dumps(event, separators=(",", ":")) for event in self._events) + "\n")
