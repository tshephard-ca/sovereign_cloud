from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import __version__
from .config import ensure_parent, model_to_dict, utc_now_iso
from .action_queue import review_queue_counts
from .impact import compute_impact, evidence_coverage_pct, evidence_slots_present
from .models import NodeEvidence, NodeInventory, QualificationPolicy, QualificationResult
from .readiness import readiness_lane_counts


BUNDLE_SCHEMA_VERSION = "rackq.evidence_bundle.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))


def build_evidence_bundle(
    evidence_dir: Path,
    policy: QualificationPolicy,
    inventory: NodeInventory | None,
    nodes: list[NodeEvidence],
    results: list[QualificationResult],
    outputs: dict[str, str],
    policy_path: Path | None = None,
    inventory_path: Path | None = None,
    redacted: bool = False,
) -> dict[str, Any]:
    node_name_map = _node_name_map(results) if redacted else {}
    results_by_name = {result.features.node_name: result for result in results}
    original_results_by_name = {_unredact_lookup_name(result.features.node_name, node_name_map): result for result in results}
    manifest_nodes: list[dict[str, Any]] = []
    for node in sorted(nodes, key=lambda item: item.node_name):
        display_name = node_name_map.get(node.node_name, node.node_name)
        result = results_by_name.get(display_name) or original_results_by_name.get(node.node_name)
        manifest_nodes.append(_node_manifest(node, display_name, result, redacted))
    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "tool": {"name": "gpu-rack-qualifier", "version": __version__},
        "mode": "REVIEW_ONLY",
        "redacted": redacted,
        "input": {
            "evidence_dir": _display_path(evidence_dir, node_name_map),
            "policy_path": str(policy_path) if policy_path else None,
            "inventory_path": str(inventory_path) if inventory_path else None,
            "policy_sha256": sha256_file(policy_path) if policy_path and policy_path.exists() else canonical_hash(model_to_dict(policy)),
            "inventory_sha256": sha256_file(inventory_path) if inventory_path and inventory_path.exists() else canonical_hash(model_to_dict(inventory)) if inventory else None,
            "policy_id": policy.policy_id,
            "cluster_id": "cluster_001" if redacted and inventory and inventory.cluster_id else inventory.cluster_id if inventory else None,
            "rack_id": "rack_001" if redacted and inventory and inventory.rack_id else inventory.rack_id if inventory else None,
        },
        "nodes": manifest_nodes,
        "outputs": outputs,
        "business_impact": compute_impact(results, nodes),
        "readiness": readiness_lane_counts(results),
        "coverage": {
            "evidence_slots_present": evidence_slots_present(nodes),
            "evidence_slots_expected": max(len(nodes) * 5, 1),
            "evidence_coverage_pct": evidence_coverage_pct(nodes),
        },
        "action_queue_counts": review_queue_counts(results),
        "caveats": [
            "Review-only output.",
            "No Slurm state was changed.",
            "No BMC or network API was called.",
            "Qualification evidence does not guarantee workload success.",
        ],
    }
    return bundle


def write_evidence_bundle(path: Path, bundle: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _node_manifest(node: NodeEvidence, display_name: str, result: QualificationResult | None, redacted: bool) -> dict[str, Any]:
    files = []
    for kind, path_text in sorted(node.source_files.items()):
        path = Path(path_text)
        if not path.exists():
            continue
        fingerprint_redacted = bool(redacted)
        files.append(
            {
                "kind": kind,
                "path": _display_path(path, {node.node_name: display_name} if redacted else {}),
                "sha256": "REDACTED" if fingerprint_redacted else sha256_file(path),
                "bytes": None if fingerprint_redacted else path.stat().st_size,
                "fingerprint_redacted": fingerprint_redacted,
            }
        )
    item: dict[str, Any] = {
        "node_name": display_name,
        "evidence_dir": _display_path(node.path, {node.node_name: display_name} if redacted else {}),
        "files": files,
    }
    if result:
        item.update(
            {
                "qualification_status": result.qualification_status,
                "confidence": result.features.confidence,
                "slurm_features": result.slurm_features,
                "reason_codes": result.features.reason_codes,
                "blockers": result.features.blockers,
                "warnings": result.features.warnings,
                "policy_decisions": result.policy_decisions,
            }
        )
    return item
def _node_name_map(results: list[QualificationResult]) -> dict[str, str]:
    original_names = sorted(result.features.node_name for result in results)
    return {name: f"node_{index:03d}" for index, name in enumerate(original_names, 1)}


def _unredact_lookup_name(name: str, mapping: dict[str, str]) -> str:
    for original, redacted in mapping.items():
        if redacted == name:
            return original
    return name


def _display_path(path: Path, mapping: dict[str, str]) -> str:
    text = str(path)
    for original, replacement in mapping.items():
        text = text.replace(original, replacement)
    return text
