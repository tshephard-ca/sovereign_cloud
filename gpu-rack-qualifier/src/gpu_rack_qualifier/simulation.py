from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .config import ensure_parent, utc_now_iso
from .evidence_loader import load_evidence
from .models import NodeInventory
from .qualification_policy import load_policy
from .rules import qualify_nodes


SIMULATION_COLUMNS = [
    "policy_path",
    "policy_id",
    "nodes_seen",
    "pass_count",
    "review_count",
    "inference_only_count",
    "avoid_multinode_count",
    "quarantine_count",
    "multinode_label_count",
    "nodes_without_multinode_label",
    "nodes_with_blockers",
    "nodes_with_warnings",
]


def simulate_policies(evidence_dir: Path, policy_paths: list[Path], inventory: NodeInventory | None = None) -> dict[str, Any]:
    simulations = []
    for policy_path in policy_paths:
        policy = load_policy(policy_path)
        nodes = load_evidence(evidence_dir, policy)
        results = qualify_nodes(nodes, policy, inventory)
        qualification = {status: sum(1 for result in results if result.qualification_status == status) for status in ["PASS", "REVIEW", "INFERENCE_ONLY", "AVOID_MULTINODE", "QUARANTINE"]}
        multinode_label_count = sum(1 for result in results if "gpu_training_multinode_ok" in result.slurm_features)
        simulations.append(
            {
                "policy_path": str(policy_path),
                "policy_id": policy.policy_id,
                "nodes_seen": len(nodes),
                "qualification": qualification,
                "labels": {
                    "gpu_training_multinode_ok": multinode_label_count,
                    "gpu_avoid_multinode": sum(1 for result in results if "gpu_avoid_multinode" in result.slurm_features),
                    "gpu_do_not_schedule": sum(1 for result in results if "gpu_do_not_schedule" in result.slurm_features),
                },
                "business_impact": {
                    "nodes_without_multinode_label": len(results) - multinode_label_count,
                    "nodes_with_blockers": sum(1 for result in results if result.features.blockers),
                    "nodes_with_warnings": sum(1 for result in results if result.features.warnings),
                },
            }
        )
    return {
        "schema_version": "rackq.policy_simulation.v1",
        "generated_at": utc_now_iso(),
        "mode": "REVIEW_ONLY",
        "simulations": simulations,
        "deltas": _deltas(simulations),
    }


def write_simulation_json(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_simulation_csv(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SIMULATION_COLUMNS)
        writer.writeheader()
        for item in report["simulations"]:
            writer.writerow(
                {
                    "policy_path": item["policy_path"],
                    "policy_id": item["policy_id"],
                    "nodes_seen": item["nodes_seen"],
                    "pass_count": item["qualification"]["PASS"],
                    "review_count": item["qualification"]["REVIEW"],
                    "inference_only_count": item["qualification"]["INFERENCE_ONLY"],
                    "avoid_multinode_count": item["qualification"]["AVOID_MULTINODE"],
                    "quarantine_count": item["qualification"]["QUARANTINE"],
                    "multinode_label_count": item["labels"]["gpu_training_multinode_ok"],
                    "nodes_without_multinode_label": item["business_impact"]["nodes_without_multinode_label"],
                    "nodes_with_blockers": item["business_impact"]["nodes_with_blockers"],
                    "nodes_with_warnings": item["business_impact"]["nodes_with_warnings"],
                }
            )


def _deltas(simulations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(simulations) < 2:
        return []
    baseline = simulations[0]
    deltas = []
    for item in simulations[1:]:
        deltas.append(
            {
                "from_policy_id": baseline["policy_id"],
                "to_policy_id": item["policy_id"],
                "pass_delta": item["qualification"]["PASS"] - baseline["qualification"]["PASS"],
                "quarantine_delta": item["qualification"]["QUARANTINE"] - baseline["qualification"]["QUARANTINE"],
                "multinode_label_delta": item["labels"]["gpu_training_multinode_ok"] - baseline["labels"]["gpu_training_multinode_ok"],
                "nodes_without_multinode_label_delta": item["business_impact"]["nodes_without_multinode_label"] - baseline["business_impact"]["nodes_without_multinode_label"],
            }
        )
    return deltas
