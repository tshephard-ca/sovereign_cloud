from __future__ import annotations

from host_screen_contracts.contract_model import ScreenFieldContract
from host_screen_contracts.field_map import FieldMap
from host_screen_contracts.flow_extract import _confidence, _expected_response_values, _matching_request_field, extract_transaction
from host_screen_contracts.models import BlockerCode, Confidence, WarningCode
from host_screen_contracts.trace_schema import ActionEvent, ActionInput, ScreenEvent, TraceField


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


def test_extract_transaction_reports_repeated_hash_and_function_key_only_screen():
    repeated = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Same"]),
        ScreenEvent(type="screen", seq=2, rows=24, cols=80, text=["Same"]),
        ActionEvent(type="action", seq=3, aid="ENTER", inputs=[{"row": 1, "col": 1, "value": "A"}]),
        ScreenEvent(type="screen", seq=4, rows=24, cols=80, text=["Done"], fields=[TraceField(row=1, col=1, length=4, value="Done", protected=True, display_only=True)]),
    ]
    result = extract_transaction(repeated, transaction_id="repeat")
    assert WarningCode.REPEATED_SCREEN_HASH.value in result.contract.warnings

    function_key_only = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["F3=Exit   F12=Cancel"], fields=[TraceField(row=1, col=1, length=1, protected=False)]),
        ActionEvent(type="action", seq=2, aid="ENTER", inputs=[{"row": 1, "col": 1, "value": "A"}]),
        ScreenEvent(type="screen", seq=3, rows=24, cols=80, text=["F3=Exit"]),
    ]
    result = extract_transaction(function_key_only, transaction_id="keys")
    assert WarningCode.FUNCTION_KEY_ONLY_SCREEN.value in result.contract.warnings

    consecutive_actions = [
        ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Start"], fields=[TraceField(row=1, col=1, length=1, protected=False)]),
        ActionEvent(type="action", seq=2, aid="ENTER", inputs=[{"row": 1, "col": 1, "value": "A"}]),
        ActionEvent(type="action", seq=3, aid="ENTER", inputs=[{"row": 1, "col": 1, "value": "B"}]),
        ScreenEvent(type="screen", seq=4, rows=24, cols=80, text=["Done"]),
    ]
    result = extract_transaction(consecutive_actions, transaction_id="bad_flow")
    assert BlockerCode.NO_FINAL_OUTPUT_FIELDS.value in result.contract.blockers


def test_flow_extract_helper_edges():
    field = ScreenFieldContract(
        name="code",
        role="input",
        screen_ref="screen_001",
        field_id="f_01_01",
        row=1,
        col=1,
        length=4,
        confidence=Confidence.MEDIUM,
        inference_source="label",
    )
    assert _confidence([], [], [field], [], plain_text_only=False) == Confidence.MEDIUM
    assert _matching_request_field(ActionInput(field_id="missing", row=2, col=2, value="A"), "screen_001", [field]) is None
    assert _matching_request_field(ActionInput(field_id="f_01_01", value="A"), "screen_999", [field]) is None
    assert _expected_response_values([], [field], FieldMap(), redact=False) == {}
