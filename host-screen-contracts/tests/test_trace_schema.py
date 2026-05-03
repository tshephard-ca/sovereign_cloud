from __future__ import annotations

import pytest

from host_screen_contracts.trace_schema import ActionInput, ScreenEvent, TraceField


def test_valid_trace_with_one_input_action_and_output(order_events):
    events = order_events
    assert [event.type for event in events] == ["screen", "action", "screen"]
    assert events[0].fields[0].id == "f_04_32"
    assert events[1].inputs[0].value == "10004567"


def test_field_ids_are_generated_from_row_col_when_absent():
    field = TraceField(row=4, col=32, length=8)
    assert field.id == "f_04_32"


def test_action_input_requires_field_reference():
    with pytest.raises(ValueError):
        ActionInput(value="x")


def test_screen_text_is_required():
    with pytest.raises(ValueError):
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=[])
