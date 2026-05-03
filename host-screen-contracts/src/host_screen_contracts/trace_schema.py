from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import generated_field_id


class Cursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int = Field(gt=0)
    col: int = Field(gt=0)


class TraceField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    row: int = Field(gt=0)
    col: int = Field(gt=0)
    length: int = Field(gt=0)
    value: str = ""
    protected: bool = False
    display_only: bool = False
    hidden: bool = False
    attributes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fill_id(self) -> "TraceField":
        if not self.id:
            self.id = generated_field_id(self.row, self.col)
        return self


class ScreenEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["screen"]
    seq: int = Field(gt=0)
    timestamp: str | None = None
    rows: int = Field(gt=0)
    cols: int = Field(gt=0)
    cursor: Cursor | None = None
    text: list[str]
    fields: list[TraceField] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def text_must_be_rows(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("screen text must contain at least one row")
        return value


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str | None = None
    row: int | None = Field(default=None, gt=0)
    col: int | None = Field(default=None, gt=0)
    value: str = ""

    @model_validator(mode="after")
    def require_reference(self) -> "ActionInput":
        if not self.field_id and (self.row is None or self.col is None):
            raise ValueError("action input requires field_id or row/col")
        return self


class ActionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["action"]
    seq: int = Field(gt=0)
    timestamp: str | None = None
    aid: str
    cursor: Cursor | None = None
    inputs: list[ActionInput] = Field(default_factory=list)

    @field_validator("aid")
    @classmethod
    def normalize_aid(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("action aid is required")
        return normalized


class NoteEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["note"]
    seq: int = Field(gt=0)
    timestamp: str | None = None
    note: str = ""


TraceEvent = ScreenEvent | ActionEvent | NoteEvent


def parse_event(data: dict[str, Any]) -> TraceEvent:
    event_type = data.get("type")
    if event_type == "screen":
        return ScreenEvent(**data)
    if event_type == "action":
        return ActionEvent(**data)
    if event_type == "note":
        return NoteEvent(**data)
    raise ValueError(f"unsupported event type: {event_type!r}")
