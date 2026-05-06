from __future__ import annotations

import pytest

from host_screen_contracts.field_map import FieldMap, FieldMapEntry, load_field_map, validate_field_map_references
from host_screen_contracts.models import FieldRole, FieldType
from host_screen_contracts.trace_schema import ScreenEvent, TraceField


def test_field_map_names_override_inferred_labels(order_result):
    result = order_result()
    assert result.contract.request_fields[0].name == "order_number"
    assert result.contract.request_fields[0].confidence == "HIGH"


def test_unknown_field_role_fails_validation():
    with pytest.raises(ValueError):
        FieldMap(fields=[{"role": "unknown", "screen_ref": "screen_001"}])


def test_unknown_field_type_fails_validation():
    with pytest.raises(ValueError):
        FieldMap(fields=[{"type": "money", "screen_ref": "screen_001"}])


def test_valid_field_map_entry_uses_enums():
    entry = FieldMapEntry(role="input", type="string")
    assert entry.role == FieldRole.INPUT
    assert entry.type == FieldType.STRING


def test_field_map_case_filtering_loading_and_reference_validation(tmp_path):
    field_map = FieldMap(
        fields=[
            FieldMapEntry(screen_ref="*", name=None, role="ignored"),
            FieldMapEntry(screen_ref="screen_001", field_id="f_01_01", name="first", role="input", case_refs=["case_a"]),
            FieldMapEntry(screen_ref="screen_002", field_id="missing", name="optional_output", role="output", required=False),
            FieldMapEntry(screen_ref="screen_003", row=99, col=1, length=1, name="bad_plain_text_coordinate", role="input"),
            FieldMapEntry(screen_ref="screen_004", field_id="missing", name="bad_field", role="input"),
            FieldMapEntry(screen_ref="screen_004", row=1, col=5, length=1, name="bad_coordinate", role="input"),
            FieldMapEntry(screen_ref="screen_999", row=1, col=1, length=1, name="unknown_screen", role="input"),
        ]
    )
    assert field_map.for_case(None) is field_map
    assert [entry.name for entry in field_map.for_case("case_a").fields if entry.name] == [
        "first",
        "optional_output",
        "bad_plain_text_coordinate",
        "bad_field",
        "bad_coordinate",
        "unknown_screen",
    ]
    assert "first" not in [entry.name for entry in field_map.for_case("case_b").fields]

    path = tmp_path / "fields.yml"
    path.write_text("transaction_id: test\nfields:\n  - screen_ref: screen_001\n    name: loaded\n    role: input\n")
    assert load_field_map(None).fields == []
    assert load_field_map(path).fields[0].name == "loaded"

    screens = [
        ("screen_001", ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=[""], fields=[TraceField(id="f_01_01", row=1, col=1, length=1)])),
        ("screen_002", ScreenEvent(type="screen", seq=2, rows=24, cols=80, text=[""], fields=[TraceField(id="f_02_01", row=2, col=1, length=1)])),
        ("screen_003", ScreenEvent(type="screen", seq=3, rows=24, cols=80, text=[""], fields=[])),
        ("screen_004", ScreenEvent(type="screen", seq=4, rows=24, cols=80, text=[""], fields=[TraceField(id="f_01_01", row=1, col=1, length=1)])),
    ]
    errors = validate_field_map_references(field_map, screens)
    assert "field map references out-of-bounds coordinate screen_003/99,1" in errors
    assert "field map references unknown field screen_004/missing" in errors
    assert "field map references unknown coordinate screen_004/1,5" in errors
    assert "field map references unknown screen_ref screen_999" in errors


def test_field_map_rejects_blank_names():
    with pytest.raises(ValueError):
        FieldMapEntry(name="   ")
