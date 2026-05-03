from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import ensure_parent, utc_now_iso
from .models import BusinessAssumptions


def build_business_impact_report(
    summary_path: Path,
    labels_path: Path,
    quarantine_path: Path,
    gpus_per_node: int | None = None,
    hours_at_risk: float | None = None,
    accelerator_hour_value: float | None = None,
) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    labels = _read_csv(labels_path)
    quarantine = _read_csv(quarantine_path)
    qualification = Counter(row["qualification_status"] for row in labels)
    recommendations = Counter(row["recommendation"] for row in quarantine)
    nodes_without_multinode = sum(1 for row in labels if "gpu_training_multinode_ok" not in row["slurm_features"].split(","))
    review_load = sum(1 for row in quarantine if row["recommendation"] != "NONE")
    assumptions = BusinessAssumptions(
        gpus_per_node=gpus_per_node,
        hours_at_risk=hours_at_risk,
        accelerator_hour_value=accelerator_hour_value,
    )
    operator_supplied_estimate = _estimated_value_at_risk(nodes_without_multinode, assumptions)
    return {
        "schema_version": "rackq.business_impact.v1",
        "generated_at": utc_now_iso(),
        "mode": "REVIEW_ONLY",
        "input_summary": {
            "cluster_id": summary.get("cluster_id"),
            "rack_id": summary.get("rack_id"),
            "nodes_seen": summary.get("input", {}).get("nodes_seen"),
            "policy_id": summary.get("policy_id"),
        },
        "impact_counters": {
            "nodes_without_multinode_label": nodes_without_multinode,
            "review_load_nodes": review_load,
            "quarantine_review_nodes": recommendations.get("QUARANTINE_REVIEW", 0),
            "avoid_multinode_nodes": recommendations.get("AVOID_MULTINODE", 0),
            "inference_only_nodes": recommendations.get("INFERENCE_ONLY", 0),
            "multinode_ready_nodes": sum(1 for row in labels if "gpu_training_multinode_ok" in row["slurm_features"].split(",")),
            "qualification": dict(sorted(qualification.items())),
            "recommendations": dict(sorted(recommendations.items())),
        },
        "operator_supplied_assumptions": _model_dict(assumptions),
        "operator_supplied_estimated_value_at_risk": operator_supplied_estimate,
        "caveats": [
            "Impact estimates are based only on operator-supplied assumptions.",
            "Counts represent review signals, not financial claims by the tool.",
            "Scheduler-facing labels remain recommendations until administrators review and apply them.",
        ],
    }


def write_business_impact_json(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_business_impact_markdown(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    lines = [
        "# Business Impact Report",
        "",
        "This report summarizes review-only qualification impact counters.",
        "",
        "## Counters",
        "",
    ]
    for key, value in report["impact_counters"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Operator-Supplied Assumptions", ""])
    for key, value in report["operator_supplied_assumptions"].items():
        lines.append(f"- {key}: {value}")
    if report["operator_supplied_estimated_value_at_risk"] is not None:
        lines.extend(["", f"- operator_supplied_estimated_value_at_risk: {report['operator_supplied_estimated_value_at_risk']}"])
    lines.extend(["", "## Caveats", ""])
    for caveat in report["caveats"]:
        lines.append(f"- {caveat}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _estimated_value_at_risk(nodes_without_multinode: int, assumptions: BusinessAssumptions) -> float | None:
    if assumptions.gpus_per_node is None or assumptions.hours_at_risk is None or assumptions.accelerator_hour_value is None:
        return None
    return round(nodes_without_multinode * assumptions.gpus_per_node * assumptions.hours_at_risk * assumptions.accelerator_hour_value, 2)


def _model_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
