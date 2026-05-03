from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import ensure_parent, utc_now_iso


BASELINE_SCHEMA_VERSION = "rackq.baseline.v1"
DRIFT_SCHEMA_VERSION = "rackq.drift.v1"


def create_baseline(summary_path: Path, labels_path: Path, quarantine_path: Path, output_path: Path) -> dict[str, Any]:
    baseline = _snapshot(summary_path, labels_path, quarantine_path)
    baseline["schema_version"] = BASELINE_SCHEMA_VERSION
    baseline["baseline_created_at"] = utc_now_iso()
    ensure_parent(output_path)
    output_path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return baseline


def compare_baseline(
    baseline_path: Path,
    current_summary_path: Path,
    current_labels_path: Path,
    current_quarantine_path: Path,
    output_json: Path,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = _snapshot(current_summary_path, current_labels_path, current_quarantine_path)
    report = _compare_snapshots(baseline, current)
    ensure_parent(output_json)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_markdown:
        write_drift_markdown(output_markdown, report)
    return report


def write_drift_markdown(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)
    lines = [
        "# Qualification Drift Report",
        "",
        "This is a review-only comparison between two qualification snapshots.",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Node Changes", ""])
    for change in report["node_changes"]:
        lines.append(f"- {change['node_name']}: {', '.join(change['changes'])}")
    lines.extend(["", "## New Blockers", ""])
    for code, count in report["new_blockers"].items():
        lines.append(f"- {code}: {count}")
    lines.extend(["", "## Drift Categories", ""])
    for code, count in report.get("drift_categories", {}).items():
        lines.append(f"- {code}: {count}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _snapshot(summary_path: Path, labels_path: Path, quarantine_path: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    labels = _read_csv(labels_path)
    quarantine = {row["node_name"]: row for row in _read_csv(quarantine_path)}
    nodes = {}
    for row in labels:
        qrow = quarantine.get(row["node_name"], {})
        nodes[row["node_name"]] = {
            "qualification_status": row["qualification_status"],
            "confidence": row["confidence"],
            "slurm_features": row["slurm_features"],
            "reason_codes": _split_codes(row["reason_codes"]),
            "blockers": _split_codes(row["blockers"]),
            "warnings": _split_codes(row["warnings"]),
            "single_node_busbw_p50_gbps": _float_or_none(row["single_node_busbw_p50_gbps"]),
            "pairwise_p50_busbw_gbps": _float_or_none(row["pairwise_p50_busbw_gbps"]),
            "recommendation": qrow.get("recommendation", ""),
            "primary_reason": qrow.get("primary_reason", ""),
        }
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "snapshot_created_at": utc_now_iso(),
        "summary": summary,
        "nodes": nodes,
    }


def _compare_snapshots(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    baseline_nodes = baseline.get("nodes", {})
    current_nodes = current.get("nodes", {})
    all_nodes = sorted(set(baseline_nodes) | set(current_nodes))
    node_changes: list[dict[str, Any]] = []
    new_blockers: Counter[str] = Counter()
    new_warnings: Counter[str] = Counter()
    drift_categories: Counter[str] = Counter()
    for node_name in all_nodes:
        before = baseline_nodes.get(node_name)
        after = current_nodes.get(node_name)
        changes: list[str] = []
        if before is None:
            changes.append("NODE_ADDED")
        elif after is None:
            changes.append("NODE_REMOVED")
        else:
            if before["qualification_status"] != after["qualification_status"]:
                changes.append(f"STATUS:{before['qualification_status']}->{after['qualification_status']}")
            if before["slurm_features"] != after["slurm_features"]:
                changes.append("SLURM_FEATURES_CHANGED")
            if _regressed(before.get("single_node_busbw_p50_gbps"), after.get("single_node_busbw_p50_gbps")):
                changes.append("SINGLE_NODE_BANDWIDTH_REGRESSION")
            if _regressed(before.get("pairwise_p50_busbw_gbps"), after.get("pairwise_p50_busbw_gbps")):
                changes.append("PAIRWISE_BANDWIDTH_REGRESSION")
                drift_categories["weak_peer_or_pairwise_regression"] += 1
            added_blockers = sorted(set(after["blockers"]) - set(before["blockers"]))
            added_warnings = sorted(set(after["warnings"]) - set(before["warnings"]))
            new_blockers.update(added_blockers)
            new_warnings.update(added_warnings)
            for code in added_blockers + added_warnings:
                category = _drift_category(code)
                if category:
                    drift_categories[category] += 1
                    changes.append(f"NEW_{category.upper()}:{code}")
        if changes:
            node_changes.append({"node_name": node_name, "changes": changes})
    return {
        "schema_version": DRIFT_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "mode": "REVIEW_ONLY",
        "counts": {
            "nodes_compared": len(all_nodes),
            "nodes_added": sum(1 for change in node_changes if "NODE_ADDED" in change["changes"]),
            "nodes_removed": sum(1 for change in node_changes if "NODE_REMOVED" in change["changes"]),
            "nodes_changed": len(node_changes),
            "new_blocker_count": sum(new_blockers.values()),
            "new_warning_count": sum(new_warnings.values()),
            "firmware_drift_count": drift_categories["firmware_drift"],
            "sensor_drift_count": drift_categories["sensor_drift"],
            "weak_peer_or_pairwise_regression_count": drift_categories["weak_peer_or_pairwise_regression"],
        },
        "node_changes": node_changes,
        "new_blockers": dict(sorted(new_blockers.items())),
        "new_warnings": dict(sorted(new_warnings.items())),
        "drift_categories": dict(sorted(drift_categories.items())),
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _split_codes(value: str) -> list[str]:
    return [code for code in value.split(";") if code]


def _float_or_none(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _regressed(before: float | None, after: float | None) -> bool:
    if before is None or after is None or before == 0:
        return False
    return after < before * 0.85


def _drift_category(code: str) -> str | None:
    if code in {"DRIVER_VERSION_MISMATCH", "CUDA_VERSION_MISMATCH", "VBIOS_MISMATCH", "VBIOS_MISMATCH_DRAIN_POLICY", "MIG_MODE_MISMATCH", "ECC_MODE_MISMATCH"}:
        return "firmware_drift"
    if code.startswith("BMC_"):
        return "sensor_drift"
    if code in {"NCCL_PAIRWISE_WEAK", "NCCL_PAIRWISE_TIMEOUT", "TOPO_WEAK_GPU_PATH", "TOPO_REVIEW_GPU_PATH"}:
        return "weak_peer_or_pairwise_regression"
    return None
