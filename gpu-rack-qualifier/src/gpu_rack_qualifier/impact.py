from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_yaml, model_to_dict
from .models import BusinessAssumptions, NodeEvidence, QualificationResult
from .readiness import readiness_lane_counts


def load_business_assumptions(path: Path | None) -> BusinessAssumptions:
    if path is None:
        return BusinessAssumptions()
    return BusinessAssumptions(**load_yaml(path))


def compute_impact(
    results: list[QualificationResult],
    nodes: list[NodeEvidence] | None = None,
    assumptions: BusinessAssumptions | None = None,
    review_questions: list[str] | None = None,
) -> dict[str, Any]:
    assumptions = assumptions or BusinessAssumptions()
    lane_counts = readiness_lane_counts(results)
    multinode_label_count = sum(1 for result in results if "gpu_training_multinode_ok" in result.slurm_features)
    action_queue_nodes = sum(1 for result in results if result.qualification_status != "PASS")
    nodes_without_multinode = len(results) - multinode_label_count
    impact: dict[str, Any] = {
        "nodes_total": len(results),
        "multinode_ready_nodes": lane_counts["MULTINODE_READY"],
        "single_node_ready_nodes": lane_counts["SINGLE_NODE_READY"],
        "inference_only_nodes": lane_counts["INFERENCE_ONLY"],
        "avoid_multinode_nodes": lane_counts["AVOID_MULTINODE"],
        "review_required_nodes": lane_counts["REVIEW_REQUIRED"],
        "quarantine_review_nodes": lane_counts["QUARANTINE_REVIEW"],
        "nodes_without_multinode_label": nodes_without_multinode,
        "action_queue_nodes": action_queue_nodes,
        "nodes_with_blockers": sum(1 for result in results if result.features.blockers),
        "nodes_with_warnings": sum(1 for result in results if result.features.warnings),
        "review_questions_generated": len(set(review_questions or [])),
        "operator_supplied_assumptions": model_to_dict(assumptions),
        "operator_supplied_estimated_value_at_risk": _estimated_value_at_risk(nodes_without_multinode, assumptions),
        "impact_note": "Counts are review signals from supplied evidence, not financial claims by the tool.",
    }
    if nodes is not None:
        impact["evidence_coverage_pct"] = evidence_coverage_pct(nodes)
        impact["evidence_slots_present"] = evidence_slots_present(nodes)
        impact["evidence_slots_expected"] = max(len(nodes) * 5, 1)
    return impact


def evidence_coverage_pct(nodes: list[NodeEvidence]) -> float:
    return round(evidence_slots_present(nodes) / max(len(nodes) * 5, 1) * 100, 2)


def evidence_slots_present(nodes: list[NodeEvidence]) -> int:
    return sum(
        [
            sum(1 for node in nodes if node.nccl_single.present),
            sum(1 for node in nodes if node.pairwise_nccl.present),
            sum(1 for node in nodes if node.topology.present),
            sum(1 for node in nodes if node.nvidia_smi_query.present),
            sum(1 for node in nodes if node.bmc_snapshot.present),
        ]
    )


def _estimated_value_at_risk(nodes_without_multinode: int, assumptions: BusinessAssumptions) -> float | None:
    if assumptions.gpus_per_node is None or assumptions.hours_at_risk is None or assumptions.accelerator_hour_value is None:
        return None
    return round(nodes_without_multinode * assumptions.gpus_per_node * assumptions.hours_at_risk * assumptions.accelerator_hour_value, 2)
