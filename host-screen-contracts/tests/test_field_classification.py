from __future__ import annotations

from host_screen_contracts.field_classification import detect_subfile_like, infer_type, response_fields_from_screens
from host_screen_contracts.field_map import FieldMap, FieldMapEntry
from host_screen_contracts.models import WarningCode
from host_screen_contracts.trace_schema import ScreenEvent, TraceField


def test_type_inference_defaults_to_string():
    assert infer_type(["ABC"])[0] == "string"


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
