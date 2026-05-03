from __future__ import annotations

from .models import DerivedNodeFeatures, QualificationPolicy


def generate_labels(status: str, features: DerivedNodeFeatures, policy: QualificationPolicy) -> list[str]:
    labels = policy.labels
    result: list[str] = []
    if status == "PASS":
        result = [
            labels.pass_label,
            labels.inference_ok_label,
            labels.single_node_training_ok_label,
            labels.multi_node_training_ok_label,
        ]
    elif status == "INFERENCE_ONLY":
        result = [labels.review_label, labels.inference_ok_label, labels.avoid_multinode_label]
    elif status == "AVOID_MULTINODE":
        result = [labels.review_label, labels.single_node_training_ok_label, labels.avoid_multinode_label]
        if features.weak_topology_path_count or features.pairwise_weak_peer_count or features.pairwise_timeout_count:
            result.append(labels.weak_link_label)
    elif status == "QUARANTINE":
        result = [labels.quarantine_label, labels.do_not_schedule_label]
        if labels.allow_inference_when_quarantined:
            result.append(labels.inference_ok_label)
        return list(dict.fromkeys(result))
    else:
        result = [labels.review_label]
        if _inference_supported(features):
            result.append(labels.inference_ok_label)
        if _single_node_training_supported(features):
            result.append(labels.single_node_training_ok_label)
        if _multinode_supported(features, policy):
            result.append(labels.multi_node_training_ok_label)
    if "VBIOS_MISMATCH" in features.reason_codes or "DRIVER_VERSION_MISMATCH" in features.reason_codes:
        result.append(labels.firmware_review_label)
    if features.bmc_warning_count or features.bmc_critical_count or features.fan_failure_count:
        result.append(labels.sensor_review_label)
    return list(dict.fromkeys(result))


def _inference_supported(features: DerivedNodeFeatures) -> bool:
    blocked = {"NCCL_CORRECTNESS_ERROR", "NCCL_WRONG_COUNT_NONZERO", "BMC_HEALTH_CRITICAL", "BMC_TEMP_CRITICAL", "BMC_FAN_FAILURE"}
    return not (set(features.blockers) & blocked) and features.gpu_count not in {None, 0}


def _single_node_training_supported(features: DerivedNodeFeatures) -> bool:
    return _inference_supported(features) and features.single_node_nccl_status == "PASS"


def _multinode_supported(features: DerivedNodeFeatures, policy: QualificationPolicy) -> bool:
    if not _single_node_training_supported(features):
        return False
    if policy.evidence.require_pairwise_nccl_for_multinode_label and features.pairwise_nccl_status != "PASS":
        return False
    return features.weak_topology_path_count == 0 and features.pairwise_timeout_count == 0 and features.pairwise_weak_peer_count == 0
