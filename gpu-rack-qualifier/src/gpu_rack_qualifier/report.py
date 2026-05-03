from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import ensure_parent, utc_now_iso
from .impact import compute_impact
from .models import BusinessAssumptions, NodeEvidence, NodeInventory, QualificationResult, SlurmLabelRow, Summary
from .quarantine import quarantine_row
from .action_queue import review_queue_counts
from .readiness import readiness_lane, readiness_lane_counts, release_lane_description


LABEL_COLUMNS = [
    "node_name",
    "qualification_status",
    "confidence",
    "slurm_features",
    "recommended_state",
    "recommended_partition_hint",
    "gpu_count",
    "expected_gpu_count",
    "single_node_busbw_p50_gbps",
    "single_node_busbw_vs_peer_median_pct",
    "pairwise_p50_busbw_gbps",
    "pairwise_weak_peer_count",
    "weak_topology_path_count",
    "bmc_warning_count",
    "bmc_critical_count",
    "firmware_mismatch_count",
    "reason_codes",
    "blockers",
    "warnings",
    "suggested_operator_question",
    "source_evidence",
]

QUARANTINE_COLUMNS = [
    "node_name",
    "recommendation",
    "severity",
    "confidence",
    "primary_reason",
    "reason_codes",
    "blockers",
    "suggested_slurm_state",
    "suggested_drain_reason",
    "safe_for_inference_candidate",
    "avoid_multinode_candidate",
    "operator_action",
    "suggested_operator_question",
    "source_evidence",
]


def label_row(result: QualificationResult) -> SlurmLabelRow:
    f = result.features
    return SlurmLabelRow(
        node_name=f.node_name,
        qualification_status=result.qualification_status,
        confidence=f.confidence,
        slurm_features=",".join(result.slurm_features),
        recommended_state=result.recommended_state,
        recommended_partition_hint=result.recommended_partition_hint,
        gpu_count=f.gpu_count,
        expected_gpu_count=f.expected_gpu_count,
        single_node_busbw_p50_gbps=f.single_node_busbw_p50_gbps,
        single_node_busbw_vs_peer_median_pct=f.single_node_busbw_vs_peer_median_pct,
        pairwise_p50_busbw_gbps=f.pairwise_p50_busbw_gbps,
        pairwise_weak_peer_count=f.pairwise_weak_peer_count,
        weak_topology_path_count=f.weak_topology_path_count,
        bmc_warning_count=f.bmc_warning_count,
        bmc_critical_count=f.bmc_critical_count,
        firmware_mismatch_count=f.firmware_mismatch_count,
        reason_codes=";".join(f.reason_codes),
        blockers=";".join(f.blockers),
        warnings=";".join(f.warnings),
        suggested_operator_question=f.suggested_operator_question or "",
        source_evidence=";".join(f.source_evidence),
    )


def write_labels_csv(path: Path, results: list[QualificationResult]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        for result in sorted(results, key=lambda item: item.features.node_name):
            writer.writerow(_model_dict(label_row(result)))


def write_quarantine_csv(path: Path, results: list[QualificationResult]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUARANTINE_COLUMNS)
        writer.writeheader()
        for result in sorted(results, key=lambda item: item.features.node_name):
            writer.writerow(_model_dict(quarantine_row(result)))


def build_summary(
    nodes: list[NodeEvidence],
    results: list[QualificationResult],
    inventory: NodeInventory | None,
    policy_id: str,
    outputs: dict[str, str],
    business_assumptions: BusinessAssumptions | None = None,
) -> Summary:
    labels_to_count = [
        "gpu_training_multinode_ok",
        "gpu_training_single_node_ok",
        "gpu_inference_ok",
        "gpu_avoid_multinode",
        "gpu_do_not_schedule",
    ]
    qualification_counts = {status: 0 for status in ["PASS", "REVIEW", "INFERENCE_ONLY", "AVOID_MULTINODE", "QUARANTINE"]}
    label_counts = {label: 0 for label in labels_to_count}
    blocker_counts: dict[str, int] = {
        "NCCL_CORRECTNESS_ERROR": 0,
        "NCCL_TIMEOUT": 0,
        "GPU_COUNT_BELOW_EXPECTED": 0,
        "BMC_HEALTH_CRITICAL": 0,
    }
    warnings: set[str] = set()
    questions: list[str] = []
    nodes_with_blockers = 0
    nodes_with_warnings = 0
    for result in results:
        qualification_counts[result.qualification_status] += 1
        for label in result.slurm_features:
            if label in label_counts:
                label_counts[label] += 1
        for blocker in result.features.blockers:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        if result.features.blockers:
            nodes_with_blockers += 1
        if result.features.warnings:
            nodes_with_warnings += 1
        warnings.update(result.features.warnings)
        if result.features.suggested_operator_question:
            questions.append(result.features.suggested_operator_question)
    expected_evidence_slots = max(len(nodes) * 5, 1)
    present_evidence_slots = sum(
        [
            sum(1 for node in nodes if node.nccl_single.present),
            sum(1 for node in nodes if node.pairwise_nccl.present),
            sum(1 for node in nodes if node.topology.present),
            sum(1 for node in nodes if node.nvidia_smi_query.present),
            sum(1 for node in nodes if node.bmc_snapshot.present),
        ]
    )
    coverage = {
        "evidence_slots_present": present_evidence_slots,
        "evidence_slots_expected": expected_evidence_slots,
        "evidence_coverage_pct": round(present_evidence_slots / expected_evidence_slots * 100, 2),
        "nodes_with_complete_core_evidence": sum(
            1
            for node in nodes
            if node.nccl_single.present and node.topology.present and node.nvidia_smi_query.present
        ),
    }
    business_impact = compute_impact(results, nodes, business_assumptions, questions)
    return Summary(
        cluster_id=inventory.cluster_id if inventory else None,
        rack_id=inventory.rack_id if inventory else None,
        generated_at=utc_now_iso(),
        policy_id=policy_id,
        input={
            "nodes_seen": len(nodes),
            "nodes_with_nccl_single": sum(1 for node in nodes if node.nccl_single.present),
            "nodes_with_nccl_pairwise": sum(1 for node in nodes if node.pairwise_nccl.present),
            "nodes_with_topo": sum(1 for node in nodes if node.topology.present),
            "nodes_with_nvidia_smi_query": sum(1 for node in nodes if node.nvidia_smi_query.present),
            "nodes_with_bmc_snapshot": sum(1 for node in nodes if node.bmc_snapshot.present),
        },
        qualification=qualification_counts,
        labels=label_counts,
        blockers=blocker_counts,
        warnings=sorted(warnings),
        top_operator_questions=sorted(set(questions))[:10],
        business_impact=business_impact,
        readiness=readiness_lane_counts(results),
        coverage=coverage,
        action_queue_counts=review_queue_counts(results),
        outputs=outputs,
    )


def write_summary_json(path: Path, summary: Summary) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(_model_dict(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown_report(summary_path: Path, labels_path: Path, quarantine_path: Path, output_path: Path) -> None:
    ensure_parent(output_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    labels = _read_csv(labels_path)
    quarantine = _read_csv(quarantine_path)
    impact = summary.get("business_impact", {})
    readiness = summary.get("readiness", {})
    action_counts = summary.get("action_queue_counts", {})
    coverage = summary.get("coverage", {})
    lines = [
        "# GPU Rack Qualification Summary",
        "",
        "This is a review-only explanation of GPU rack qualification evidence. It is not live scheduler enforcement.",
        "",
        "## Executive Summary",
        "",
        f"- nodes seen: {summary.get('input', {}).get('nodes_seen', len(labels))}",
        f"- multi-node-ready nodes: {readiness.get('MULTINODE_READY', summary.get('labels', {}).get('gpu_training_multinode_ok', 0))}",
        f"- nodes withheld from multi-node training: {impact.get('nodes_without_multinode_label', 0)}",
        f"- action queue nodes: {action_counts.get('total', 0)}",
        f"- quarantine-review nodes: {impact.get('quarantine_review_nodes', 0)}",
        f"- evidence coverage: {coverage.get('evidence_coverage_pct', impact.get('evidence_coverage_pct', 'unknown'))}%",
        "",
        "## Workload Readiness",
        "",
    ]
    for lane, count in readiness.items():
        lines.append(f"- {lane}: {count} - {release_lane_description(lane)}")
    lines.extend(["", "## Business Impact", ""])
    for key in [
        "nodes_without_multinode_label",
        "avoid_multinode_nodes",
        "inference_only_nodes",
        "quarantine_review_nodes",
        "nodes_with_blockers",
        "nodes_with_warnings",
        "operator_supplied_estimated_value_at_risk",
    ]:
        if key in impact:
            lines.append(f"- {key}: {impact[key]}")
    lines.extend(["", "## Action Queue", ""])
    actionable = [row for row in quarantine if row["recommendation"] != "NONE"]
    if actionable:
        for row in actionable[:20]:
            lane = _lane_for_node(labels, row["node_name"])
            lines.append(f"- {row['node_name']}: {lane} because `{row['primary_reason']}` - {row['operator_action']}")
        if len(actionable) > 20:
            lines.append(f"- {len(actionable) - 20} additional action-queue nodes are listed in the CSV outputs.")
    else:
        lines.append("- No action-queue nodes from current evidence.")
    lines.extend(["", "## Node Labels", ""])
    for row in labels[:20]:
        lane = _lane_for_node(labels, row["node_name"])
        lines.append(f"- {row['node_name']}: {lane} / {row['qualification_status']} ({row['confidence']}) `{row['slurm_features']}`")
    if len(labels) > 20:
        lines.append(f"- {len(labels) - 20} additional node label rows are listed in the CSV outputs.")
    lines.extend(["", "## Review Recommendations", ""])
    if actionable:
        for row in actionable[:20]:
            lines.append(f"- {row['node_name']}: {row['recommendation']} because `{row['primary_reason']}`")
        if len(actionable) > 20:
            lines.append(f"- {len(actionable) - 20} additional review recommendations are listed in the CSV outputs.")
    else:
        lines.append("- No quarantine-review candidates from current evidence.")
    lines.extend(["", "## Operator Questions", ""])
    for question in summary.get("top_operator_questions", []):
        lines.append(f"- {question}")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- NCCL all-reduce is useful communication evidence, not a complete burn-in.",
            "- Topology evidence is context, not performance proof.",
            "- Peer-relative thresholds can hide rack-wide underperformance.",
            "- Sensor snapshots are point-in-time evidence.",
            "- Slurm labels remain recommendations until reviewed and applied by administrators.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _lane_for_node(labels: list[dict[str, str]], node_name: str) -> str:
    row = next((item for item in labels if item["node_name"] == node_name), None)
    if row is None:
        return "REVIEW_REQUIRED"
    status = row["qualification_status"]
    features = row.get("slurm_features", "").split(",")
    if status == "PASS":
        return "MULTINODE_READY"
    if status == "AVOID_MULTINODE":
        return "AVOID_MULTINODE"
    if status == "INFERENCE_ONLY":
        return "INFERENCE_ONLY"
    if status == "QUARANTINE":
        return "QUARANTINE_REVIEW"
    if "gpu_training_single_node_ok" in features:
        return "SINGLE_NODE_READY"
    return "REVIEW_REQUIRED"


def _model_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
