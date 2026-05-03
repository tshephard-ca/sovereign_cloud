from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import FieldRole, FieldType
from .trace_schema import ScreenEvent, TraceField


class VolatileRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screen_ref: str = "*"
    row: int = Field(gt=0)
    col: int = Field(gt=0)
    length: int = Field(gt=0)
    reason: str = "volatile"


class FieldMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screen_ref: str = "*"
    field_id: str | None = None
    row: int | None = Field(default=None, gt=0)
    col: int | None = Field(default=None, gt=0)
    length: int | None = Field(default=None, gt=0)
    name: str | None = None
    role: FieldRole | None = None
    type: FieldType | None = None
    required: bool | None = None
    sensitive: bool | None = None
    optional: bool = False
    case_refs: list[str] = Field(default_factory=list)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        name = value.strip()
        if not name:
            raise ValueError("field map name cannot be blank")
        return name


class FieldMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str | None = None
    display_name: str | None = None
    endpoint_path: str | None = None
    volatile_regions: list[VolatileRegion] = Field(default_factory=list)
    fields: list[FieldMapEntry] = Field(default_factory=list)

    def entries_for(self, screen_ref: str) -> list[FieldMapEntry]:
        return [entry for entry in self.fields if entry.screen_ref in (screen_ref, "*")]

    def for_case(self, case_id: str | None) -> "FieldMap":
        if not case_id:
            return self
        return self.model_copy(
            update={
                "fields": [
                    entry
                    for entry in self.fields
                    if not entry.case_refs or case_id in entry.case_refs
                ]
            }
        )

    def find_for_field(self, screen_ref: str, field: TraceField) -> FieldMapEntry | None:
        for entry in self.entries_for(screen_ref):
            if entry.field_id and entry.field_id == field.id:
                return entry
            if entry.row == field.row and entry.col == field.col:
                return entry
        return None

    def find_by_reference(
        self,
        screen_ref: str,
        field_id: str | None = None,
        row: int | None = None,
        col: int | None = None,
    ) -> FieldMapEntry | None:
        for entry in self.entries_for(screen_ref):
            if field_id and entry.field_id == field_id:
                return entry
            if row is not None and col is not None and entry.row == row and entry.col == col:
                return entry
        return None

    def volatile_for(self, screen_ref: str) -> list[VolatileRegion]:
        return [region for region in self.volatile_regions if region.screen_ref in (screen_ref, "*")]


def load_field_map(path: str | Path | None) -> FieldMap:
    if path is None:
        return FieldMap()
    data = yaml.safe_load(Path(path).read_text()) or {}
    return FieldMap(**data)


def validate_field_map_references(field_map: FieldMap, screens: list[tuple[str, ScreenEvent]]) -> list[str]:
    screen_lookup = {screen_ref: screen for screen_ref, screen in screens}
    errors: list[str] = []
    for entry in field_map.fields:
        if entry.screen_ref == "*":
            continue
        screen = screen_lookup.get(entry.screen_ref)
        if screen is None:
            errors.append(f"field map references unknown screen_ref {entry.screen_ref}")
            continue
        if not screen.fields:
            if entry.row is not None and entry.col is not None:
                if entry.row > screen.rows or entry.col > screen.cols:
                    errors.append(f"field map references out-of-bounds coordinate {entry.screen_ref}/{entry.row},{entry.col}")
            continue
        if entry.field_id:
            if not any(field.id == entry.field_id for field in screen.fields):
                if not _entry_may_be_absent(entry):
                    errors.append(f"field map references unknown field {entry.screen_ref}/{entry.field_id}")
        elif entry.row is not None and entry.col is not None:
            if not any(field.row == entry.row and field.col == entry.col for field in screen.fields):
                if not _entry_may_be_absent(entry):
                    errors.append(f"field map references unknown coordinate {entry.screen_ref}/{entry.row},{entry.col}")
    return errors


def _entry_may_be_absent(entry: FieldMapEntry) -> bool:
    if entry.optional:
        return True
    if entry.role == FieldRole.ERROR_MESSAGE:
        return True
    if entry.role in (FieldRole.OUTPUT, FieldRole.INPUT_OUTPUT, FieldRole.HIDDEN) and entry.required is False:
        return True
    return False
