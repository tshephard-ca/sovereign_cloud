from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import ensure_parent, utc_now_iso
from .evidence_loader import load_evidence
from .models import NodeInventory, QualificationPolicy
from .rules import qualify_nodes


def build_coverage_report(
    evidence_dir: Path,
    policy: QualificationPolicy,
    inventory: NodeInventory | None = None,
    labels_path: Path | None = None,
    quarantine_path: Path | None = None,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    nodes = load_evidence(evidence_dir, policy)
    results = qualify_nodes(nodes, policy, inventory)
    labels = _read_csv(labels_path) if labels_path and labels_path.exists() else []
    quarantine = _read_csv(quarantine_path) if quarantine_path and quarantine_path.exists() else []
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path and summary_path.exists() else {}
    node_count = len(nodes)
    file_coverage = {
        "nccl_single_node_all_reduce": _pct(sum(node.nccl_single.present for node in nodes), node_count),
        "nccl_pairwise_all_reduce": _pct(sum(node.pairwise_nccl.present for node in nodes), node_count),
        "nvidia_smi_topo_m": _pct(sum(node.topology.present for node in nodes), node_count),
        "nvidia_smi_topo_p2p_n": _pct(sum("p2p_topology" in node.source_files for node in nodes), node_count),
        "nvidia_smi_query_xml": _pct(sum(node.nvidia_smi_query.present for node in nodes), node_count),
        "bmc_sensors_redfish_json": _pct(sum(node.bmc_snapshot.present for node in nodes), node_count),
        "collection_metadata_json": _pct(sum("collection_metadata" in node.source_files for node in nodes), node_count),
    }
    parse_status = {
        "nccl_single": dict(sorted(Counter(node.nccl_single.status for node in nodes).items())),
        "pairwise_nccl": dict(sorted(Counter(node.pairwise_nccl.status for node in nodes).items())),
        "topology_parsed": dict(sorted(Counter(str(node.topology.parsed) for node in nodes).items())),
        "nvidia_smi_query_parsed": dict(sorted(Counter(str(node.nvidia_smi_query.parsed) for node in nodes).items())),
        "bmc_snapshot_parsed": dict(sorted(Counter(str(node.bmc_snapshot.parsed) for node in nodes).items())),
    }
    signal_coverage = {
        "weak_pairwise_nodes": sum(node.pairwise_nccl.status == "WEAK" for node in nodes),
        "pairwise_timeout_nodes": sum(node.pairwise_nccl.timeout_count > 0 for node in nodes),
        "weak_topology_nodes": sum(node.topology.weak_gpu_path_count > 0 for node in nodes),
        "review_topology_nodes": sum(node.topology.review_gpu_path_count > 0 for node in nodes),
        "p2p_missing_nodes": sum(node.topology.p2p_nvlink_missing_count > 0 for node in nodes),
        "bmc_warning_nodes": sum(node.bmc_snapshot.warning_count > 0 for node in nodes),
        "bmc_critical_nodes": sum(node.bmc_snapshot.critical_count > 0 for node in nodes),
        "fan_failure_nodes": sum(node.bmc_snapshot.fan_failure_count > 0 for node in nodes),
        "temperature_warning_or_critical_nodes": sum((node.bmc_snapshot.temp_max_celsius or 0) >= policy.sensors.temp_warning_celsius for node in nodes),
        "temperature_critical_nodes": sum((node.bmc_snapshot.temp_max_celsius or 0) >= policy.sensors.temp_critical_celsius for node in nodes),
        "gpu_count_below_expected_nodes": sum("GPU_COUNT_BELOW_EXPECTED" in result.features.blockers for result in results),
        "driver_mismatch_nodes": sum("DRIVER_VERSION_MISMATCH" in result.features.reason_codes for result in results),
        "cuda_mismatch_nodes": sum("CUDA_VERSION_MISMATCH" in result.features.reason_codes for result in results),
        "vbios_mismatch_nodes": sum("VBIOS_MISMATCH" in result.features.reason_codes for result in results),
        "ecc_mismatch_nodes": sum("ECC_MODE_MISMATCH" in result.features.reason_codes for result in results),
        "mig_mismatch_nodes": sum("MIG_MODE_MISMATCH" in result.features.reason_codes for result in results),
        "malformed_nccl_nodes": sum("NCCL_PARSE_FAILED" in result.features.reason_codes for result in results),
        "malformed_xml_nodes": sum("NVIDIA_SMI_QUERY_PARSE_FAILED" in result.features.reason_codes for result in results),
    }
    output_coverage = _output_coverage(labels, quarantine, summary)
    gaps = _coverage_gaps(file_coverage, parse_status, signal_coverage, labels, quarantine, summary)
    return {
        "schema_version": "rackq.coverage_report.v1",
        "generated_at": utc_now_iso(),
        "mode": "REVIEW_ONLY",
        "input": {
            "evidence_dir": str(evidence_dir),
            "nodes_seen": node_count,
            "inventory_nodes": len(inventory.nodes) if inventory else None,
            "policy_id": policy.policy_id,
        },
        "file_coverage_pct": file_coverage,
        "parse_status": parse_status,
        "signal_coverage": signal_coverage,
        "output_coverage": output_coverage,
        "data_gaps": gaps,
    }


def write_coverage_json(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_coverage_markdown(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    lines = [
        "# Qualification Coverage Report",
        "",
        "This report describes evidence coverage, parsed signal coverage, output coverage, and remaining data gaps.",
        "",
        "## Inputs",
        "",
        f"- nodes_seen: {report['input']['nodes_seen']}",
        f"- inventory_nodes: {report['input']['inventory_nodes']}",
        f"- policy_id: {report['input']['policy_id']}",
        "",
        "## File Coverage",
        "",
    ]
    for key, value in report["file_coverage_pct"].items():
        lines.append(f"- {key}: {value}%")
    lines.extend(["", "## Signal Coverage", ""])
    for key, value in report["signal_coverage"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Output Coverage", ""])
    for key, value in report["output_coverage"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Data Gaps", ""])
    for gap in report["data_gaps"]:
        lines.append(f"- {gap}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _output_coverage(labels: list[dict[str, str]], quarantine: list[dict[str, str]], summary: dict[str, Any]) -> dict[str, Any]:
    label_status = Counter(row.get("qualification_status", "") for row in labels)
    recommendations = Counter(row.get("recommendation", "") for row in quarantine)
    return {
        "label_rows": len(labels),
        "quarantine_rows": len(quarantine),
        "qualification_statuses": dict(sorted((key, value) for key, value in label_status.items() if key)),
        "quarantine_recommendations": dict(sorted((key, value) for key, value in recommendations.items() if key)),
        "business_impact_present": bool(summary.get("business_impact")),
        "portfolio_ready": bool(labels and quarantine and summary),
    }


def _coverage_gaps(
    file_coverage: dict[str, float],
    parse_status: dict[str, dict[str, int]],
    signal_coverage: dict[str, int],
    labels: list[dict[str, str]],
    quarantine: list[dict[str, str]],
    summary: dict[str, Any],
) -> list[str]:
    gaps: list[str] = []
    for key, pct in file_coverage.items():
        if pct < 100:
            gaps.append(f"{key} coverage is {pct}%, so reports should explain missing evidence")
    if parse_status["topology_parsed"].get("False"):
        gaps.append("some topology files are missing or unparsed")
    if parse_status["nvidia_smi_query_parsed"].get("False"):
        gaps.append("some nvidia-smi XML files are malformed or unparsed")
    if signal_coverage["weak_pairwise_nodes"] == 0:
        gaps.append("no weak pairwise NCCL signal is represented")
    if signal_coverage["bmc_critical_nodes"] == 0:
        gaps.append("no BMC critical sensor signal is represented")
    if signal_coverage["malformed_nccl_nodes"] == 0:
        gaps.append("no malformed NCCL evidence is represented")
    if signal_coverage["malformed_xml_nodes"] == 0:
        gaps.append("no malformed nvidia-smi XML evidence is represented")
    if not labels:
        gaps.append("labels CSV was not supplied, so output coverage cannot be evaluated")
    if not quarantine:
        gaps.append("quarantine CSV was not supplied, so review recommendations cannot be evaluated")
    if not summary:
        gaps.append("summary JSON was not supplied, so business-impact counters cannot be evaluated")
    return gaps or ["no coverage gaps detected by current checks"]


def _pct(value: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(value / total * 100, 2)


def _read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
