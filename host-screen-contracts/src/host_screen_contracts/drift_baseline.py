from __future__ import annotations

from typing import Any

from .contract_model import TransactionContract


def generate_drift_baseline(contract: TransactionContract) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_by": "host-screen-contracts",
        "transaction_id": contract.transaction_id,
        "display_name": contract.display_name,
        "endpoint_path": contract.endpoint_path,
        "confidence": contract.confidence.value,
        "screen_count": len(contract.screens),
        "transition_count": len(contract.transitions),
        "replay_case_count": len(contract.replay_cases),
        "screens": [
            {
                "screen_ref": screen.screen_ref,
                "screen_hash": screen.screen_hash,
                "normalized_text_hash": screen.normalized_text_hash,
                "field_layout_hash": screen.field_layout_hash,
                "cursor_hash": screen.cursor_hash,
                "title": screen.title,
                "rows": screen.rows,
                "cols": screen.cols,
                "function_keys": screen.function_keys,
                "field_count": len(screen.fields),
                "subfile_region_count": len(screen.subfile_regions),
            }
            for screen in contract.screens
        ],
        "transitions": [
            {
                "from_screen_ref": transition.from_screen_ref,
                "aid": transition.aid,
                "to_screen_ref": transition.to_screen_ref,
                "expected_to_screen_hash": transition.expected_to_screen_hash,
            }
            for transition in contract.transitions
        ],
        "replay_cases": [
            {
                "case_id": replay_case.case_id,
                "case_kind": replay_case.case_kind,
                "start_screen_hash": replay_case.start_screen_hash,
            }
            for replay_case in contract.replay_cases
        ],
        "flow_graph": contract.flow_graph,
        "volatile_regions": contract.volatile_regions,
        "warnings": contract.warnings,
        "blockers": contract.blockers,
        "comparison_policy": {
            "field_layout_hash_change": "breaking",
            "normalized_text_hash_change": "review",
            "screen_hash_change": "review",
            "transition_aid_change": "breaking",
        },
    }
