from __future__ import annotations

from host_screen_contracts.models import BlockerCode
from host_screen_contracts.trace_schema import ActionEvent, ScreenEvent
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
