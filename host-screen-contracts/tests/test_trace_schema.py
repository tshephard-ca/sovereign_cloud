from __future__ import annotations

import pytest

from host_screen_contracts.parse_trace import TraceParseError, action_events, load_trace, note_events, screen_events
from host_screen_contracts.trace_schema import ActionEvent, ActionInput, ScreenEvent, TraceField, parse_event


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


def test_action_aid_is_normalized_and_required():
    assert ActionEvent(type="action", seq=1, aid=" enter ", inputs=[{"field_id": "f_01_01", "value": "A"}]).aid == "ENTER"
    with pytest.raises(ValueError):
        ActionEvent(type="action", seq=1, aid=" ")


def test_parse_event_and_load_trace_handle_notes_blank_lines_and_errors(tmp_path):
    assert parse_event({"type": "note", "seq": 1, "note": "operator note"}).type == "note"
    with pytest.raises(ValueError):
        parse_event({"type": "unknown", "seq": 1})

    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "\n"
        '{"type":"screen","seq":1,"rows":24,"cols":80,"text":["START"]}\n'
        '{"type":"note","seq":2,"note":"between"}\n'
        '{"type":"action","seq":3,"aid":"ENTER","inputs":[]}\n'
    )
    events = load_trace(trace)
    assert len(events) == 3
    assert len(screen_events(events)) == 1
    assert len(note_events(events)) == 1
    assert len(action_events(events)) == 1

    bad = tmp_path / "bad.trace.jsonl"
    bad.write_text("not-json\n")
    with pytest.raises(TraceParseError):
        load_trace(bad)
