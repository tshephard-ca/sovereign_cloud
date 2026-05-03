from __future__ import annotations

import pytest

from host_screen_contracts.field_map import FieldMap, FieldMapEntry
from host_screen_contracts.models import FieldRole, FieldType


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
