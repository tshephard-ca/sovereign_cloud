from __future__ import annotations

from .models import DerivedNodeFeatures


def evaluate_policy_decisions(features: DerivedNodeFeatures, status: str) -> list[dict[str, object]]:
    decisions: list[dict[str, object]] = []
    decisions.append(
        {
            "rule_id": f"STATUS_{status}",
            "severity": _status_severity(status),
            "action": status,
            "evidence": {
                "single_node_nccl_status": features.single_node_nccl_status,
                "pairwise_nccl_status": features.pairwise_nccl_status,
                "confidence": features.confidence,
            },
            "reason_codes": list(features.reason_codes),
        }
    )
    for blocker in features.blockers:
        decisions.append(
            {
                "rule_id": f"BLOCKER_{blocker}",
                "severity": "CRITICAL",
                "action": "PREVENT_NORMAL_TRAINING_PLACEMENT",
                "evidence": _feature_evidence(features, blocker),
                "reason_codes": [blocker],
            }
        )
    for warning in features.warnings:
        decisions.append(
            {
                "rule_id": f"WARNING_{warning}",
                "severity": "WARNING",
                "action": "HUMAN_REVIEW",
                "evidence": _feature_evidence(features, warning),
                "reason_codes": [warning],
            }
        )
    return decisions


def _status_severity(status: str) -> str:
    return {
        "PASS": "INFO",
        "REVIEW": "REVIEW",
        "INFERENCE_ONLY": "WARNING",
        "AVOID_MULTINODE": "WARNING",
        "QUARANTINE": "CRITICAL",
    }.get(status, "REVIEW")


def _feature_evidence(features: DerivedNodeFeatures, code: str) -> dict[str, object]:
    mapping = {
        "NCCL_TIMEOUT": {"single_node_nccl_status": features.single_node_nccl_status, "pairwise_timeout_count": features.pairwise_timeout_count},
        "NCCL_CORRECTNESS_ERROR": {"single_node_nccl_status": features.single_node_nccl_status},
        "NCCL_WRONG_COUNT_NONZERO": {"single_node_nccl_status": features.single_node_nccl_status},
        "NCCL_PAIRWISE_WEAK": {"pairwise_p50_busbw_gbps": features.pairwise_p50_busbw_gbps, "pairwise_weak_peer_count": features.pairwise_weak_peer_count},
        "NCCL_PAIRWISE_MISSING": {"pairwise_nccl_status": features.pairwise_nccl_status},
        "GPU_COUNT_BELOW_EXPECTED": {"gpu_count": features.gpu_count, "expected_gpu_count": features.expected_gpu_count},
        "BMC_HEALTH_CRITICAL": {"bmc_critical_count": features.bmc_critical_count},
        "BMC_HEALTH_WARNING": {"bmc_warning_count": features.bmc_warning_count},
        "BMC_TEMP_CRITICAL": {"temp_max_celsius": features.temp_max_celsius},
        "BMC_TEMP_WARNING": {"temp_max_celsius": features.temp_max_celsius},
        "BMC_FAN_FAILURE": {"fan_failure_count": features.fan_failure_count},
        "TOPO_WEAK_GPU_PATH": {"weak_topology_path_count": features.weak_topology_path_count},
        "TOPO_REVIEW_GPU_PATH": {"review_topology_path_count": features.review_topology_path_count},
        "VBIOS_MISMATCH": {"vbios_versions": features.vbios_versions},
        "VBIOS_MISMATCH_DRAIN_POLICY": {"vbios_versions": features.vbios_versions},
        "DRIVER_VERSION_MISMATCH": {"driver_version": features.driver_version},
        "CUDA_VERSION_MISMATCH": {"cuda_version": features.cuda_version},
    }
    return mapping.get(code, {"confidence": features.confidence})
