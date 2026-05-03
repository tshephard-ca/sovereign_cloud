from __future__ import annotations

from .features import derive_features, driver_baselines
from .labels import generate_labels
from .models import NodeEvidence, NodeInventory, QualificationPolicy, QualificationResult
from .policy_engine import evaluate_policy_decisions
from .scoring import compute_peer_median


def qualify_nodes(nodes: list[NodeEvidence], policy: QualificationPolicy, inventory: NodeInventory | None = None) -> list[QualificationResult]:
    peer_median = compute_peer_median(nodes)
    driver_baseline, cuda_baseline = driver_baselines(nodes)
    results: list[QualificationResult] = []
    for evidence in sorted(nodes, key=lambda node: node.node_name):
        features = derive_features(evidence, policy, inventory, peer_median, driver_baseline, cuda_baseline)
        status = _status_from_features(features, policy)
        labels = generate_labels(status, features, policy)
        recommended_state = _recommended_state(status, features)
        results.append(
            QualificationResult(
                features=features,
                qualification_status=status,
                slurm_features=labels,
                recommended_state=recommended_state,
                recommended_partition_hint=_partition_hint(status),
                policy_decisions=evaluate_policy_decisions(features, status),
            )
        )
    return results


def _status_from_features(features, policy: QualificationPolicy) -> str:
    if _has_quarantine_blocker(features.blockers):
        features.reason_codes.append("LABEL_QUARANTINE")
        return "QUARANTINE"
    single_ok = features.single_node_nccl_status == "PASS"
    pairwise_ok = features.pairwise_nccl_status == "PASS"
    pairwise_missing = "NCCL_PAIRWISE_MISSING" in features.warnings
    multinode_risk = (
        features.pairwise_nccl_status in {"WEAK", "TIMEOUT"}
        or features.pairwise_timeout_count > 0
        or features.pairwise_weak_peer_count > 0
        or features.weak_topology_path_count > 0
        or (policy.topology.require_nvlink_for_multinode_training and "TOPO_WEAK_GPU_PATH" in features.warnings)
    )
    if single_ok and multinode_risk:
        features.reason_codes.append("LABEL_AVOID_MULTINODE")
        return "AVOID_MULTINODE"
    if single_ok and pairwise_missing and policy.evidence.require_pairwise_nccl_for_multinode_label:
        features.reason_codes.append("LABEL_INFERENCE_OK")
        return "INFERENCE_ONLY"
    if single_ok and (pairwise_ok or not policy.evidence.require_pairwise_nccl_for_multinode_label) and not features.warnings:
        features.reason_codes.append("LABEL_MULTI_NODE_TRAINING_OK")
        return "PASS"
    if single_ok and not features.blockers:
        features.reason_codes.append("LABEL_REVIEW")
        return "REVIEW"
    if not single_ok and not features.blockers:
        features.reason_codes.append("LABEL_REVIEW")
        return "REVIEW"
    features.reason_codes.append("LABEL_QUARANTINE")
    return "QUARANTINE"


def _has_quarantine_blocker(blockers: list[str]) -> bool:
    quarantine_blockers = {
        "NCCL_CORRECTNESS_ERROR",
        "NCCL_TIMEOUT",
        "NCCL_WRONG_COUNT_NONZERO",
        "GPU_COUNT_BELOW_EXPECTED",
        "BMC_HEALTH_CRITICAL",
        "BMC_FAN_FAILURE",
        "BMC_TEMP_CRITICAL",
        "VBIOS_MISMATCH_DRAIN_POLICY",
    }
    return bool(set(blockers) & quarantine_blockers)


def _recommended_state(status: str, features) -> str:
    if status == "PASS":
        return "KEEP"
    if status == "QUARANTINE":
        return "QUARANTINE_REVIEW"
    if "DRAIN_REVIEW_RECOMMENDED" in features.reason_codes:
        return "DRAIN_REVIEW"
    return "REVIEW"


def _partition_hint(status: str) -> str:
    return {
        "PASS": "training",
        "REVIEW": "review",
        "INFERENCE_ONLY": "inference",
        "AVOID_MULTINODE": "single-node-or-inference",
        "QUARANTINE": "do-not-schedule",
    }[status]
