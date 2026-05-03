from __future__ import annotations

from host_screen_contracts.field_map import FieldMap
from host_screen_contracts.flow_extract import extract_transaction
from host_screen_contracts.models import BlockerCode, WarningCode
from host_screen_contracts.trace_schema import ActionEvent, ScreenEvent, TraceField


def test_request_fields_are_extracted_from_action_inputs(order_result):
    fields = order_result().contract.request_fields
    assert len(fields) == 1
    assert fields[0].name == "order_number"


def test_plain_text_only_trace_requires_field_map_for_strict_extraction():
    events = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Code . . . . . . . . . .  ____"]),
        ActionEvent(type="action", seq=2, aid="ENTER", inputs=[{"row": 1, "col": 29, "value": "A001"}]),
        ScreenEvent(type="screen", seq=3, rows=24, cols=80, text=["Result . . . . . . . . .  OK"]),
    ]
    result = extract_transaction(events, transaction_id="plain", field_map=FieldMap(), strict=True)
    assert BlockerCode.NO_FINAL_OUTPUT_FIELDS.value in result.contract.blockers


def test_strict_mode_fails_on_generated_coordinate_only_field_names():
    events = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["                               ____"], fields=[TraceField(row=1, col=32, length=4, protected=False)]),
        ActionEvent(type="action", seq=2, aid="ENTER", inputs=[{"row": 1, "col": 32, "value": "A001"}]),
        ScreenEvent(type="screen", seq=3, rows=24, cols=80, text=["                               OK"], fields=[TraceField(row=1, col=32, length=2, value="OK", protected=True, display_only=True)]),
    ]
    result = extract_transaction(events, transaction_id="coord", strict=True)
    assert BlockerCode.GENERATED_COORDINATE_NAMES_IN_STRICT_MODE.value in result.contract.blockers


def test_non_strict_mode_permits_coordinate_names_with_low_confidence():
    events = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["                               ____"], fields=[TraceField(row=1, col=32, length=4, protected=False)]),
        ActionEvent(type="action", seq=2, aid="ENTER", inputs=[{"row": 1, "col": 32, "value": "A001"}]),
        ScreenEvent(type="screen", seq=3, rows=24, cols=80, text=["                               OK"], fields=[TraceField(row=1, col=32, length=2, value="OK", protected=True, display_only=True)]),
    ]
    result = extract_transaction(events, transaction_id="coord", strict=False)
    assert result.contract.request_fields[0].name == "field_01_32"
    assert result.contract.confidence == "LOW"
    assert WarningCode.GENERATED_COORDINATE_NAMES.value in result.contract.warnings


def test_subfile_like_screen_adds_extraction_warning():
    events = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Opt  Id", "_ 001", "_ 002", "_ 003", "_ 004"], fields=[TraceField(row=2, col=1, length=1, protected=False)]),
        ActionEvent(type="action", seq=2, aid="ENTER", inputs=[{"row": 2, "col": 1, "value": "1"}]),
        ScreenEvent(type="screen", seq=3, rows=24, cols=80, text=["Result . . . . . . . . .  OK"], fields=[TraceField(row=1, col=29, length=2, value="OK", protected=True, display_only=True)]),
    ]
    result = extract_transaction(events, transaction_id="list_select")
    assert WarningCode.SUBFILE_LIKE_REGION_DETECTED.value in result.contract.warnings


def test_summary_json_contains_expected_counts(order_result):
    summary = order_result().summary
    assert summary["screen_count"] == 2
    assert summary["action_count"] == 1
    assert summary["request_field_count"] == 1
    assert summary["response_field_count"] == 2
