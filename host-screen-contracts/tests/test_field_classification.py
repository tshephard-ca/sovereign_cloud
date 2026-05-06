from __future__ import annotations

from host_screen_contracts.field_classification import (
    detect_error_screen,
    detect_subfile_like,
    fields_for_screen,
    find_field,
    infer_type,
    request_fields_from_actions,
    response_fields_from_screens,
    text_span,
)
from host_screen_contracts.field_map import FieldMap, FieldMapEntry
from host_screen_contracts.models import WarningCode
from host_screen_contracts.trace_schema import ActionInput, ScreenEvent, TraceField


def test_type_inference_defaults_to_string():
    assert infer_type(["ABC"])[0] == "string"
    assert infer_type(["2026-01-15"])[1] == "date"
    assert infer_type(["12:00"], FieldMapEntry(type="time")) == ("string", "time", None, "field_map")
    assert infer_type(["2026-01-15T12:00:00Z"], FieldMapEntry(type="datetime")) == ("string", "date-time", None, "field_map")


def test_numeric_business_identifiers_remain_strings_unless_field_map_says_integer():
    field_type, field_format, pattern, source = infer_type(["00123"])
    assert (field_type, field_format, pattern, source) == ("string", None, "^[0-9]+$", "observed_value")
    assert infer_type(["00123"], FieldMapEntry(type="integer"))[0] == "integer"


def test_response_fields_are_extracted_from_mapped_final_screen(order_result):
    fields = order_result().contract.response_fields
    assert [field.name for field in fields] == ["customer_name", "order_status"]


def test_function_key_footer_text_is_not_treated_as_output_field():
    screen = ScreenEvent(
        type="screen",
        seq=3,
        rows=24,
        cols=80,
        text=["F3=Exit"],
        fields=[TraceField(id="f_01_01", row=1, col=1, length=7, value="F3=Exit", protected=True, display_only=True)],
    )
    fields, _warnings = response_fields_from_screens([("screen_003", screen)], FieldMap())
    assert fields == []


def test_subfile_like_screen_triggers_warning():
    screen = ScreenEvent(
        type="screen",
        seq=1,
        rows=24,
        cols=80,
        text=[
            "Opt  Id      Name",
            "_    001     ROW",
            "_    002     ROW",
            "_    003     ROW",
            "_    004     ROW",
            "More...",
        ],
    )
    assert detect_subfile_like(screen)


def test_field_classification_edge_helpers():
    screen = ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Code  ____", "Footer"], fields=[])
    assert text_span(screen, 99, 1, 1) == ""
    field_map = FieldMap(
        fields=[
            FieldMapEntry(screen_ref="screen_001", name="incomplete", role="output"),
            FieldMapEntry(screen_ref="screen_001", row=1, col=7, length=4, name="code", role="input_output", required=False, sensitive=False),
        ]
    )
    fields = fields_for_screen("screen_001", screen, field_map)
    assert fields[0].id == "f_01_07"
    assert fields[0].value == ""
    assert find_field("screen_001", screen, FieldMap(), row=1, col=20, fallback_value="ABC").length == 3
    assert find_field("screen_001", screen, FieldMap()) is None

    request_fields, warnings = request_fields_from_actions(
        [
            ("screen_001", screen, []),
            ("screen_001", screen, [ActionInput(field_id="missing", value="A")]),
            ("screen_001", screen, [ActionInput(row=1, col=7, value="A"), ActionInput(row=1, col=7, value="A"), ActionInput(row=3, col=20, value="B")]),
        ],
        field_map,
    )
    assert len(request_fields) == 2
    assert WarningCode.FIELD_NAMES_INFERRED.value in warnings

    assert detect_error_screen(ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Permission denied"]))


def test_response_fields_with_missing_mapped_targets_are_skipped():
    screen = ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["Result OK"], fields=[TraceField(id="f_01_08", row=1, col=8, length=2, value="OK", protected=True, display_only=True)])
    field_map = FieldMap(fields=[FieldMapEntry(screen_ref="screen_999", row=1, col=1, length=1, name="missing", role="output")])
    fields, warnings = response_fields_from_screens([("screen_001", screen)], field_map)
    assert fields
    assert WarningCode.OUTPUT_FIELD_SELECTION_REQUIRES_REVIEW.value in warnings
