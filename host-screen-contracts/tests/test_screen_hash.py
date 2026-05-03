from __future__ import annotations

from host_screen_contracts.field_map import FieldMap, VolatileRegion
from host_screen_contracts.screen_hash import compute_screen_hashes
from host_screen_contracts.trace_schema import ScreenEvent, TraceField


def test_screen_hash_ignores_user_entered_input_values():
    first_row = "Name . . . . . . . . . .".ljust(29) + "ALPHA"
    second_row = "Name . . . . . . . . . .".ljust(29) + "BRAVO"
    first = ScreenEvent(
        type="screen",
        seq=1,
        rows=24,
        cols=80,
        text=[first_row],
        fields=[TraceField(id="f_01_30", row=1, col=30, length=5, value="ALPHA", protected=False)],
    )
    second = first.model_copy(
        update={
            "text": [second_row],
            "fields": [TraceField(id="f_01_30", row=1, col=30, length=5, value="BRAVO", protected=False)],
        }
    )
    assert compute_screen_hashes(first, "screen_001").screen_hash == compute_screen_hashes(second, "screen_001").screen_hash


def test_screen_hash_changes_when_protected_label_text_changes():
    first = ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["ORDER DETAIL"])
    second = ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["ORDER SUMMARY"])
    assert compute_screen_hashes(first, "screen_001").screen_hash != compute_screen_hashes(second, "screen_001").screen_hash


def test_volatile_regions_are_excluded_from_hash():
    fmap = FieldMap(volatile_regions=[VolatileRegion(screen_ref="*", row=1, col=65, length=15)])
    first = ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["SESSION                                                       12:00:00"])
    second = ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["SESSION                                                       12:01:00"])
    assert compute_screen_hashes(first, "screen_001", fmap).screen_hash == compute_screen_hashes(second, "screen_001", fmap).screen_hash
