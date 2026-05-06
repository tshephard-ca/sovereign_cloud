from __future__ import annotations

from host_screen_contracts.field_map import FieldMap, FieldMapEntry
from host_screen_contracts.models import BlockerCode, WarningCode
from host_screen_contracts.trace_schema import ActionEvent, ScreenEvent, TraceField
from host_screen_contracts.validate_trace import validate_trace


def test_validate_trace_passes_for_valid_jsonl(order_events):
    result = validate_trace(order_events, strict=True)
    assert result.ok
    assert result.blockers == []


def test_validate_trace_fails_when_no_screen_events_exist():
    result = validate_trace([ActionEvent(type="action", seq=1, aid="ENTER")], strict=True)
    assert BlockerCode.NO_SCREEN_EVENTS.value in result.blockers


def test_validate_trace_fails_when_action_not_followed_by_screen_in_strict_mode():
    events = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Start"]),
        ActionEvent(type="action", seq=2, aid="ENTER"),
    ]
    result = validate_trace(events, strict=True)
    assert BlockerCode.TRACE_SEQUENCE_INVALID.value in result.blockers


def test_validate_trace_reports_size_aid_bounds_and_field_map_modes():
    no_action = validate_trace([ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Start"])])
    assert BlockerCode.NO_ACTION_EVENTS.value in no_action.blockers

    sized = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Start"]),
        ActionEvent(type="action", seq=2, aid="ROLLUP"),
        ScreenEvent(type="screen", seq=3, rows=27, cols=132, text=["Wide"]),
    ]
    non_strict = validate_trace(sized, strict=False, screen_size=(24, 80))
    strict = validate_trace(sized, strict=True, screen_size=(24, 80))
    assert BlockerCode.SCREEN_SIZE_INVALID.value in non_strict.warnings
    assert WarningCode.UNSUPPORTED_AID.value in non_strict.warnings
    assert BlockerCode.SCREEN_SIZE_INVALID.value in strict.blockers
    assert BlockerCode.TRACE_SEQUENCE_INVALID.value in strict.blockers

    out_of_bounds = validate_trace(
        [
            ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Start"], fields=[TraceField(row=25, col=1, length=1)]),
            ActionEvent(type="action", seq=2, aid="ENTER"),
            ScreenEvent(type="screen", seq=3, rows=24, cols=80, text=["Done"]),
        ]
    )
    assert BlockerCode.FIELD_COORDINATES_OUT_OF_BOUNDS.value in out_of_bounds.blockers

    field_map = FieldMap(fields=[FieldMapEntry(screen_ref="screen_001", field_id="missing", name="bad", role="input")])
    events = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Start"], fields=[TraceField(id="f_01_01", row=1, col=1, length=1)]),
        ActionEvent(type="action", seq=2, aid="ENTER"),
        ScreenEvent(type="screen", seq=3, rows=24, cols=80, text=["Done"]),
    ]
    assert BlockerCode.FIELD_MAP_INVALID.value in validate_trace(events, field_map=field_map).warnings
    assert BlockerCode.FIELD_MAP_INVALID.value in validate_trace(events, field_map=field_map, strict=True).blockers
