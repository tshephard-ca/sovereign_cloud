from __future__ import annotations

from pydantic import BaseModel, Field

from .field_map import FieldMap, validate_field_map_references
from .models import BlockerCode, SUPPORTED_AIDS, WarningCode, screen_ref_for_seq
from .parse_trace import action_events, screen_events
from .trace_schema import ActionEvent, ScreenEvent, TraceEvent


class ValidationResult(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers


def _next_non_note(events: list[TraceEvent], start: int) -> TraceEvent | None:
    for event in events[start:]:
        if event.type != "note":
            return event
    return None


def _field_in_bounds(screen: ScreenEvent) -> bool:
    for field in screen.fields:
        if field.row > screen.rows:
            return False
        if field.col > screen.cols:
            return False
        if field.col + field.length - 1 > screen.cols:
            return False
    return True


def validate_trace(
    events: list[TraceEvent],
    *,
    strict: bool = False,
    screen_size: tuple[int, int] | None = None,
    field_map: FieldMap | None = None,
) -> ValidationResult:
    warnings: list[str] = []
    blockers: list[str] = []

    screens = screen_events(events)
    actions = action_events(events)

    if not screens:
        blockers.append(BlockerCode.NO_SCREEN_EVENTS.value)
    if not actions:
        blockers.append(BlockerCode.NO_ACTION_EVENTS.value)

    seqs = [event.seq for event in events]
    if seqs != sorted(seqs) or len(seqs) != len(set(seqs)):
        blockers.append(BlockerCode.TRACE_SEQUENCE_INVALID.value)

    expected_size = screen_size
    if expected_size is None and screens:
        expected_size = (screens[0].rows, screens[0].cols)
    for screen in screens:
        if expected_size and (screen.rows, screen.cols) != expected_size:
            if strict:
                blockers.append(BlockerCode.SCREEN_SIZE_INVALID.value)
            else:
                warnings.append(BlockerCode.SCREEN_SIZE_INVALID.value)
        if not _field_in_bounds(screen):
            blockers.append(BlockerCode.FIELD_COORDINATES_OUT_OF_BOUNDS.value)
    if screens and all(not screen.fields for screen in screens):
        warnings.append(WarningCode.PLAIN_TEXT_ONLY_TRACE.value)

    for index, event in enumerate(events):
        if isinstance(event, ActionEvent):
            next_event = _next_non_note(events, index + 1)
            if not isinstance(next_event, ScreenEvent):
                if strict:
                    blockers.append(BlockerCode.TRACE_SEQUENCE_INVALID.value)
                else:
                    warnings.append(BlockerCode.TRACE_SEQUENCE_INVALID.value)
            if event.aid not in SUPPORTED_AIDS:
                if strict:
                    blockers.append(BlockerCode.TRACE_SEQUENCE_INVALID.value)
                else:
                    warnings.append(WarningCode.UNSUPPORTED_AID.value)

    if field_map is not None:
        ref_screens = [(screen_ref_for_seq(screen.seq), screen) for screen in screens]
        map_errors = validate_field_map_references(field_map, ref_screens)
        if map_errors and strict:
            blockers.append(BlockerCode.FIELD_MAP_INVALID.value)
        elif map_errors:
            warnings.append(BlockerCode.FIELD_MAP_INVALID.value)

    return ValidationResult(
        warnings=sorted(set(warnings), key=warnings.index),
        blockers=sorted(set(blockers), key=blockers.index),
    )
