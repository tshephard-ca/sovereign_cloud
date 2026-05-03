from __future__ import annotations

from typing import Any

from .contract_model import TransactionContract


def build_flow_graph(contract_cases: list[tuple[str, str, TransactionContract]]) -> dict[str, Any]:
    nodes_by_hash: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    for case_id, case_kind, contract in contract_cases:
        screen_hash_by_ref = {screen.screen_ref: screen.screen_hash for screen in contract.screens}
        for screen in contract.screens:
            node = nodes_by_hash.setdefault(
                screen.screen_hash,
                {
                    "screen_hash": screen.screen_hash,
                    "screen_refs": [],
                    "titles": [],
                    "rows": screen.rows,
                    "cols": screen.cols,
                },
            )
            if screen.screen_ref not in node["screen_refs"]:
                node["screen_refs"].append(screen.screen_ref)
            if screen.title and screen.title not in node["titles"]:
                node["titles"].append(screen.title)

        for index, transition in enumerate(contract.transitions, start=1):
            edges.append(
                {
                    "edge_id": f"{case_id}:{index}",
                    "case_id": case_id,
                    "case_kind": case_kind,
                    "from_screen_ref": transition.from_screen_ref,
                    "from_screen_hash": screen_hash_by_ref.get(transition.from_screen_ref, ""),
                    "aid": transition.aid,
                    "to_screen_ref": transition.to_screen_ref,
                    "to_screen_hash": transition.expected_to_screen_hash,
                    "input_names": sorted(transition.input_values),
                }
            )

        cases.append(
            {
                "case_id": case_id,
                "case_kind": case_kind,
                "start_screen_hash": contract.screens[0].screen_hash if contract.screens else "",
                "end_screen_hash": contract.screens[-1].screen_hash if contract.screens else "",
                "transition_count": len(contract.transitions),
                "warnings": contract.warnings,
                "blockers": contract.blockers,
            }
        )

    return {
        "schema_version": "1.0",
        "graph_kind": "recorded_trace_cases",
        "node_count": len(nodes_by_hash),
        "edge_count": len(edges),
        "case_count": len(cases),
        "nodes": sorted(nodes_by_hash.values(), key=lambda node: node["screen_hash"]),
        "edges": edges,
        "cases": cases,
    }
