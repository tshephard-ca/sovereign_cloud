from __future__ import annotations

from typing import Any

from .config import ExtractionConfig, DEFAULT_CONFIG
from .contract_model import ScreenContract, TransactionContract
from .field_map import FieldMap
from .models import screen_ref_for_seq
from .screen_hash import compute_screen_hashes
from .trace_schema import ActionEvent, ScreenEvent, TraceEvent


def _field_lookup(screen: ScreenEvent) -> dict[str, tuple[int, int, int, bool, bool, bool]]:
    return {
        field.id or f"f_{field.row:02d}_{field.col:02d}": (
            field.row,
            field.col,
            field.length,
            field.protected,
            field.display_only,
            field.hidden,
        )
        for field in screen.fields
    }


def _contract_field_lookup(screen: ScreenContract) -> dict[str, tuple[int, int, int]]:
    return {
        field.field_id or f"f_{field.row:02d}_{field.col:02d}": (field.row, field.col, field.length)
        for field in screen.fields
    }


def compare_contract_to_trace(
    contract: TransactionContract,
    events: list[TraceEvent],
    *,
    field_map: FieldMap | None = None,
    config: ExtractionConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    field_map = field_map or FieldMap(
        volatile_regions=[],
        fields=[],
    )
    trace_screens = [(screen_ref_for_seq(event.seq), event) for event in events if isinstance(event, ScreenEvent)]
    trace_actions = [event for event in events if isinstance(event, ActionEvent)]
    changes: list[dict[str, Any]] = []
    contract_by_ref = {screen.screen_ref: screen for screen in contract.screens}

    if len(trace_screens) != len(contract.screens):
        changes.append(
            {
                "kind": "screen_count_changed",
                "expected": len(contract.screens),
                "actual": len(trace_screens),
                "severity": "breaking",
            }
        )

    for index, (screen_ref, screen) in enumerate(trace_screens):
        expected = contract_by_ref.get(screen_ref)
        if expected is None and index < len(contract.screens):
            expected = contract.screens[index]
        if expected is None:
            changes.append({"kind": "unknown_screen", "screen_ref": screen_ref, "severity": "breaking"})
            continue
        current_hashes = compute_screen_hashes(screen, expected.screen_ref, field_map, config)
        if current_hashes.field_layout_hash != expected.field_layout_hash:
            changes.append(
                {
                    "kind": "layout_changed",
                    "screen_ref": expected.screen_ref,
                    "expected": expected.field_layout_hash,
                    "actual": current_hashes.field_layout_hash,
                    "severity": "breaking",
                }
            )
        elif current_hashes.normalized_text_hash != expected.normalized_text_hash:
            changes.append(
                {
                    "kind": "labels_changed",
                    "screen_ref": expected.screen_ref,
                    "expected": expected.normalized_text_hash,
                    "actual": current_hashes.normalized_text_hash,
                    "severity": "review",
                }
            )
        elif current_hashes.screen_hash != expected.screen_hash:
            changes.append(
                {
                    "kind": "screen_hash_changed",
                    "screen_ref": expected.screen_ref,
                    "expected": expected.screen_hash,
                    "actual": current_hashes.screen_hash,
                    "severity": "review",
                }
            )

        trace_fields = _field_lookup(screen)
        for field_id, expected_location in _contract_field_lookup(expected).items():
            actual = trace_fields.get(field_id)
            if actual is None:
                continue
            actual_location = actual[:3]
            if actual_location != expected_location:
                changes.append(
                    {
                        "kind": "field_moved_or_resized",
                        "screen_ref": expected.screen_ref,
                        "field_id": field_id,
                        "expected": {
                            "row": expected_location[0],
                            "col": expected_location[1],
                            "length": expected_location[2],
                        },
                        "actual": {"row": actual_location[0], "col": actual_location[1], "length": actual_location[2]},
                        "severity": "breaking",
                    }
                )

    action_aids = [action.aid for action in trace_actions]
    transition_aids = [transition.aid for transition in contract.transitions]
    if action_aids != transition_aids:
        changes.append(
            {
                "kind": "replay_path_changed",
                "expected": transition_aids,
                "actual": action_aids,
                "severity": "breaking",
            }
        )

    has_breaking = any(change["severity"] == "breaking" for change in changes)
    has_review = any(change["severity"] == "review" for change in changes)
    status = "compatible"
    if has_breaking:
        status = "breaking_change"
    elif has_review:
        status = "review_required"
    return {
        "schema_version": "1.0",
        "transaction_id": contract.transaction_id,
        "status": status,
        "compatible": status == "compatible",
        "change_count": len(changes),
        "changes": changes,
        "screen_count": len(trace_screens),
        "action_count": len(trace_actions),
        "hash_context": "field_map_supplied" if field_map.fields or field_map.volatile_regions else "contract_only",
    }
