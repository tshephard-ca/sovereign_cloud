from __future__ import annotations

import re
from collections import Counter

from .models import DerivedNodeFeatures, NodeEvidence, NodeInventory, QualificationPolicy
from .scoring import pct_of_peer, sorted_unique


def derive_features(
    evidence: NodeEvidence,
    policy: QualificationPolicy,
    inventory: NodeInventory | None = None,
    peer_median: float | None = None,
    driver_baseline: str | None = None,
    cuda_baseline: str | None = None,
) -> DerivedNodeFeatures:
    inv_entry = inventory.by_name().get(evidence.node_name) if inventory else None
    expected = inventory.expected if inventory else None
    expected_gpu_count = (
        inv_entry.expected_gpu_count
        if inv_entry and inv_entry.expected_gpu_count is not None
        else expected.gpu_count
        if expected and expected.gpu_count is not None
        else None
    )
    gpus = evidence.nvidia_smi_query.gpus
    gpu_count = len(gpus) if evidence.nvidia_smi_query.parsed else None
    features = DerivedNodeFeatures(
        node_name=evidence.node_name,
        gpu_count=gpu_count,
        expected_gpu_count=expected_gpu_count,
        gpu_count_ok=(gpu_count == expected_gpu_count) if gpu_count is not None and expected_gpu_count is not None else None,
        driver_version=evidence.nvidia_smi_query.driver_version,
        cuda_version=evidence.nvidia_smi_query.cuda_version,
        vbios_versions=sorted_unique([gpu.vbios_version or "" for gpu in gpus]),
        vbios_consistent_within_node=(len(set(gpu.vbios_version for gpu in gpus if gpu.vbios_version)) <= 1) if gpus else None,
        mig_mode_summary=_summarize([gpu.mig_mode for gpu in gpus]),
        ecc_mode_summary=_summarize([gpu.ecc_mode for gpu in gpus]),
        single_node_nccl_status=evidence.nccl_single.status,
        single_node_busbw_best_gbps=_round(evidence.nccl_single.best_bandwidth_gbps),
        single_node_busbw_p50_gbps=_round(evidence.nccl_single.p50_bandwidth_gbps),
        single_node_busbw_vs_peer_median_pct=pct_of_peer(evidence.nccl_single.p50_bandwidth_gbps, peer_median),
        pairwise_nccl_status=evidence.pairwise_nccl.status,
        pairwise_weak_peer_count=evidence.pairwise_nccl.weak_peer_count,
        pairwise_timeout_count=evidence.pairwise_nccl.timeout_count,
        pairwise_min_busbw_gbps=_round(evidence.pairwise_nccl.min_busbw_gbps),
        pairwise_p50_busbw_gbps=_round(evidence.pairwise_nccl.p50_busbw_gbps),
        weak_topology_path_count=evidence.topology.weak_gpu_path_count,
        review_topology_path_count=evidence.topology.review_gpu_path_count,
        p2p_nvlink_missing_count=evidence.topology.p2p_nvlink_missing_count,
        bmc_warning_count=evidence.bmc_snapshot.warning_count,
        bmc_critical_count=evidence.bmc_snapshot.critical_count,
        fan_failure_count=evidence.bmc_snapshot.fan_failure_count,
        temp_max_celsius=_round(evidence.bmc_snapshot.temp_max_celsius),
        source_evidence=sorted(evidence.source_files.values()),
    )
    _add_evidence_reasons(features, evidence, policy, inventory is not None)
    _add_hardware_reasons(features, evidence, policy, expected, driver_baseline, cuda_baseline)
    _add_nccl_reasons(features, evidence, policy, peer_median)
    _add_topology_reasons(features, evidence, policy)
    _add_sensor_reasons(features, evidence, policy)
    _add_parser_reasons(features, evidence)
    _set_confidence(features, policy)
    features.reason_codes = sorted_unique(features.reason_codes)
    features.blockers = sorted_unique(features.blockers)
    features.warnings = sorted_unique(features.warnings)
    features.suggested_operator_question = suggested_operator_question(features.reason_codes + features.blockers + features.warnings)
    return features


def driver_baselines(nodes: list[NodeEvidence]) -> tuple[str | None, str | None]:
    drivers = Counter(node.nvidia_smi_query.driver_version for node in nodes if node.nvidia_smi_query.driver_version)
    cudas = Counter(node.nvidia_smi_query.cuda_version for node in nodes if node.nvidia_smi_query.cuda_version)
    return (drivers.most_common(1)[0][0] if drivers else None, cudas.most_common(1)[0][0] if cudas else None)


def _add_evidence_reasons(features: DerivedNodeFeatures, evidence: NodeEvidence, policy: QualificationPolicy, inventory_present: bool) -> None:
    checks = [
        ("nccl_single", evidence.nccl_single.present, policy.evidence.require_nccl_single_node, "NCCL_SINGLE_NODE_PRESENT", "NCCL_SINGLE_NODE_MISSING", "NCCL_REQUIRED_BUT_MISSING"),
        ("pairwise_nccl", evidence.pairwise_nccl.present, policy.evidence.require_pairwise_nccl_for_multinode_label, "NCCL_PAIRWISE_PRESENT", "NCCL_PAIRWISE_MISSING", None),
        ("topology", evidence.topology.present, policy.evidence.require_topo, "TOPO_PRESENT", "TOPO_MISSING", "TOPOLOGY_REQUIRED_BUT_MISSING"),
        ("nvidia_smi_query", evidence.nvidia_smi_query.present, policy.evidence.require_nvidia_smi_query, "NVIDIA_SMI_QUERY_PRESENT", "NVIDIA_SMI_QUERY_MISSING", "HARDWARE_IDENTITY_UNKNOWN"),
        ("bmc_snapshot", evidence.bmc_snapshot.present, policy.evidence.require_bmc_snapshot, "BMC_SNAPSHOT_PRESENT", "BMC_SNAPSHOT_MISSING", None),
    ]
    missing_required = False
    for name, present, required, present_code, missing_code, blocker in checks:
        if present:
            features.evidence_present.append(name)
            features.reason_codes.append(present_code)
        else:
            features.reason_codes.append(missing_code)
            if required:
                missing_required = True
                if blocker:
                    features.warnings.append(blocker)
            else:
                features.warnings.append(missing_code)
    features.reason_codes.append("INVENTORY_PRESENT" if inventory_present else "INVENTORY_MISSING")
    if not inventory_present:
        features.warnings.append("INVENTORY_MISSING")
    features.reason_codes.append("EVIDENCE_PARTIAL" if missing_required else "EVIDENCE_COMPLETE")
    if missing_required:
        features.warnings.append("PARTIAL_EVIDENCE")


def _add_hardware_reasons(
    features: DerivedNodeFeatures,
    evidence: NodeEvidence,
    policy: QualificationPolicy,
    expected: object | None,
    driver_baseline: str | None,
    cuda_baseline: str | None,
) -> None:
    if features.expected_gpu_count is not None:
        if features.gpu_count is None:
            features.reason_codes.append("GPU_COUNT_MISSING")
            features.warnings.append("GPU_COUNT_MISSING")
        elif features.gpu_count < features.expected_gpu_count:
            features.reason_codes.append("GPU_COUNT_BELOW_EXPECTED")
            features.blockers.append("GPU_COUNT_BELOW_EXPECTED")
        else:
            features.reason_codes.append("GPU_COUNT_OK")
    elif features.gpu_count is None:
        features.reason_codes.append("GPU_COUNT_MISSING")
        features.warnings.append("GPU_COUNT_MISSING")
    if expected and getattr(expected, "driver_version", None):
        if features.driver_version is not None and not _version_matches(features.driver_version, getattr(expected, "driver_version")):
            features.reason_codes.append("DRIVER_VERSION_MISMATCH")
            features.warnings.append("DRIVER_VERSION_MISMATCH")
        elif features.driver_version is not None:
            features.reason_codes.append("DRIVER_VERSION_OK")
    elif policy.firmware.require_driver_consistency_across_rack and driver_baseline and features.driver_version and features.driver_version != driver_baseline:
        features.reason_codes.append("DRIVER_VERSION_MISMATCH")
        features.warnings.append("DRIVER_VERSION_MISMATCH")
    elif features.driver_version:
        features.reason_codes.append("DRIVER_VERSION_OK")
    if expected and getattr(expected, "cuda_version", None):
        if features.cuda_version is not None and not _version_matches(features.cuda_version, getattr(expected, "cuda_version")):
            features.reason_codes.append("CUDA_VERSION_MISMATCH")
            features.warnings.append("CUDA_VERSION_MISMATCH")
    elif policy.firmware.require_driver_consistency_across_rack and cuda_baseline and features.cuda_version and features.cuda_version != cuda_baseline:
        features.reason_codes.append("CUDA_VERSION_MISMATCH")
        features.warnings.append("CUDA_VERSION_MISMATCH")
    if policy.firmware.require_vbios_consistency_within_node:
        if features.vbios_consistent_within_node:
            features.reason_codes.append("VBIOS_CONSISTENT")
        elif features.vbios_consistent_within_node is False:
            features.reason_codes.append("VBIOS_MISMATCH")
            features.firmware_mismatch_count += 1
            if policy.firmware.vbios_mismatch_action == "DRAIN_REVIEW" or policy.quarantine.drain_on_vbios_mismatch:
                features.blockers.append("VBIOS_MISMATCH_DRAIN_POLICY")
                features.reason_codes.append("DRAIN_REVIEW_RECOMMENDED")
            else:
                features.warnings.append("VBIOS_MISMATCH")
    if expected and getattr(expected, "mig_mode", None) and features.mig_mode_summary and features.mig_mode_summary.lower() != str(getattr(expected, "mig_mode")).lower():
        features.reason_codes.append("MIG_MODE_MISMATCH")
        features.warnings.append("MIG_MODE_MISMATCH")
    if expected and getattr(expected, "ecc_mode", None) and features.ecc_mode_summary and features.ecc_mode_summary.lower() != str(getattr(expected, "ecc_mode")).lower():
        features.reason_codes.append("ECC_MODE_MISMATCH")
        features.warnings.append("ECC_MODE_MISMATCH")
    if any(gpu.retired_pages > 0 for gpu in evidence.nvidia_smi_query.gpus):
        features.reason_codes.append("RETIRED_PAGES_OBSERVED")
        features.warnings.append("RETIRED_PAGES_OBSERVED")
    if any(gpu.clocks_throttle_reasons for gpu in evidence.nvidia_smi_query.gpus):
        features.reason_codes.append("CLOCK_THROTTLE_OBSERVED")
        features.warnings.append("CLOCK_THROTTLE_OBSERVED")


def _add_nccl_reasons(features: DerivedNodeFeatures, evidence: NodeEvidence, policy: QualificationPolicy, peer_median: float | None) -> None:
    features.reason_codes.extend(evidence.nccl_single.reason_codes)
    features.reason_codes.extend(evidence.pairwise_nccl.reason_codes)
    if "NCCL_PARSE_FAILED" in evidence.nccl_single.reason_codes or "NCCL_PARSE_FAILED" in evidence.pairwise_nccl.reason_codes:
        features.warnings.append("NCCL_PARSE_FAILED")
    if "NCCL_SMALL_SAMPLE" in evidence.nccl_single.reason_codes or "NCCL_SMALL_SAMPLE" in evidence.pairwise_nccl.reason_codes:
        features.warnings.append("NCCL_SMALL_SAMPLE")
    if evidence.nccl_single.timeout and policy.nccl.timeout_is_quarantine:
        features.blockers.append("NCCL_TIMEOUT")
    if evidence.nccl_single.correctness_error and policy.nccl.correctness_error_is_quarantine:
        features.blockers.append("NCCL_CORRECTNESS_ERROR")
    if evidence.nccl_single.wrong_count_total and policy.nccl.wrong_count_is_quarantine:
        features.blockers.append("NCCL_WRONG_COUNT_NONZERO")
    if policy.nccl.min_single_node_busbw_gbps is not None and features.single_node_busbw_p50_gbps is not None:
        if features.single_node_busbw_p50_gbps < policy.nccl.min_single_node_busbw_gbps:
            features.reason_codes.append("NCCL_SINGLE_NODE_WARN")
            features.warnings.append("NCCL_SINGLE_NODE_WARN")
    elif policy.nccl.min_single_node_busbw_gbps is None and peer_median is None:
        features.warnings.append("NO_ABSOLUTE_THRESHOLD")
    if features.single_node_busbw_vs_peer_median_pct is None:
        if evidence.nccl_single.parsed:
            features.reason_codes.append("NCCL_NO_PEER_MEDIAN")
            features.warnings.append("PEER_MEDIAN_SMALL_SAMPLE")
    else:
        pct = features.single_node_busbw_vs_peer_median_pct
        if pct < policy.nccl.peer_median_fail_pct:
            features.reason_codes.append("NCCL_BELOW_PEER_MEDIAN_FAIL")
            features.warnings.append("NCCL_BELOW_PEER_MEDIAN_FAIL")
        elif pct < policy.nccl.peer_median_warning_pct:
            features.reason_codes.append("NCCL_BELOW_PEER_MEDIAN_WARNING")
            features.warnings.append("NCCL_BELOW_PEER_MEDIAN_WARNING")
    if evidence.pairwise_nccl.timeout_count:
        features.warnings.append("NCCL_PAIRWISE_TIMEOUT")
    if evidence.pairwise_nccl.status == "WEAK":
        features.warnings.append("NCCL_PAIRWISE_WEAK")
    if not evidence.pairwise_nccl.present and policy.evidence.require_pairwise_nccl_for_multinode_label:
        features.warnings.append("NCCL_PAIRWISE_MISSING")


def _add_topology_reasons(features: DerivedNodeFeatures, evidence: NodeEvidence, policy: QualificationPolicy) -> None:
    features.reason_codes.extend(evidence.topology.reason_codes)
    if features.weak_topology_path_count:
        features.warnings.append("TOPO_WEAK_GPU_PATH")
    if features.review_topology_path_count:
        features.warnings.append("TOPO_REVIEW_GPU_PATH")
    if policy.topology.p2p_nvlink_expected and features.p2p_nvlink_missing_count:
        features.warnings.append("TOPO_P2P_NVLINK_MISSING")
    if policy.topology.require_nvlink_for_multinode_training and evidence.topology.present and evidence.topology.nvlink_path_count == 0:
        features.reason_codes.append("TOPO_WEAK_GPU_PATH")
        features.warnings.append("TOPO_WEAK_GPU_PATH")


def _add_sensor_reasons(features: DerivedNodeFeatures, evidence: NodeEvidence, policy: QualificationPolicy) -> None:
    features.reason_codes.extend(evidence.bmc_snapshot.reason_codes)
    if features.bmc_critical_count and policy.sensors.health_critical_action == "QUARANTINE":
        features.blockers.append("BMC_HEALTH_CRITICAL")
    if features.bmc_warning_count:
        features.warnings.append("BMC_HEALTH_WARNING")
    if features.fan_failure_count and policy.sensors.fan_failure_action == "QUARANTINE":
        features.blockers.append("BMC_FAN_FAILURE")
    if features.temp_max_celsius is not None:
        if features.temp_max_celsius >= policy.sensors.temp_critical_celsius:
            features.reason_codes.append("BMC_TEMP_CRITICAL")
            features.blockers.append("BMC_TEMP_CRITICAL")
        elif features.temp_max_celsius >= policy.sensors.temp_warning_celsius:
            features.reason_codes.append("BMC_TEMP_WARNING")
            features.warnings.append("BMC_TEMP_WARNING")
    if evidence.bmc_snapshot.power_critical_count:
        features.reason_codes.append("BMC_POWER_CRITICAL")
        if policy.sensors.power_critical_action == "QUARANTINE":
            features.blockers.append("BMC_POWER_CRITICAL")
    if evidence.bmc_snapshot.power_warning_count:
        features.reason_codes.append("BMC_POWER_WARNING")
        features.warnings.append("BMC_POWER_WARNING")


def _add_parser_reasons(features: DerivedNodeFeatures, evidence: NodeEvidence) -> None:
    features.reason_codes.extend(evidence.nvidia_smi_query.reason_codes)
    if "NVIDIA_SMI_QUERY_PARSE_FAILED" in evidence.nvidia_smi_query.reason_codes:
        features.warnings.append("NVIDIA_SMI_QUERY_PARSE_FAILED")
    features.reason_codes.extend(evidence.bmc_snapshot.reason_codes)
    if "BMC_SENSOR_PARSE_FAILED" in evidence.bmc_snapshot.reason_codes:
        features.warnings.append("BMC_SENSOR_PARSE_FAILED")


def _set_confidence(features: DerivedNodeFeatures, policy: QualificationPolicy) -> None:
    missing_core = {
        "NCCL_SINGLE_NODE_MISSING",
        "TOPO_MISSING",
        "NVIDIA_SMI_QUERY_MISSING",
        "GPU_COUNT_MISSING",
        "NCCL_PARSE_FAILED",
        "TOPO_PARSE_FAILED",
        "NVIDIA_SMI_QUERY_PARSE_FAILED",
    }
    missing_count = len(set(features.reason_codes) & missing_core)
    if missing_count >= 2 or "HARDWARE_IDENTITY_UNKNOWN" in features.blockers:
        features.confidence = "LOW"
    elif missing_count == 1 or "NCCL_PAIRWISE_MISSING" in features.warnings or "PEER_MEDIAN_SMALL_SAMPLE" in features.warnings:
        features.confidence = "MEDIUM"
    else:
        features.confidence = "HIGH"
    if policy.evidence.require_pairwise_nccl_for_multinode_label and "NCCL_PAIRWISE_MISSING" in features.warnings:
        features.confidence = "MEDIUM" if features.confidence == "HIGH" else features.confidence


def suggested_operator_question(codes: list[str]) -> str | None:
    questions = {
        "NCCL_PAIRWISE_WEAK": "Does this node have weaker pairwise NCCL performance with all peers or only specific peers?",
        "NCCL_TIMEOUT": "Did the timeout reproduce on a second run, and does it correlate with a specific peer or fabric path?",
        "NCCL_CORRECTNESS_ERROR": "Should this node be removed from scheduling until GPU, driver, and fabric health are validated?",
        "TOPO_WEAK_GPU_PATH": "Is this topology expected for the server model, or does it indicate a cabling/riser/fabric issue?",
        "GPU_COUNT_BELOW_EXPECTED": "Is the node intentionally configured with fewer GPUs, or is a GPU missing from the host?",
        "VBIOS_MISMATCH": "Is mixed VBIOS expected for this node, or should firmware be aligned before training placement?",
        "DRIVER_VERSION_MISMATCH": "Is this driver version intentionally different from the rack baseline?",
        "BMC_HEALTH_WARNING": "Is the warning transient, acknowledged, or recurring under load?",
        "BMC_HEALTH_CRITICAL": "Should scheduling be stopped until the critical BMC sensor state is cleared?",
        "BMC_TEMP_WARNING": "Does temperature rise under NCCL load, and is airflow/cooling within site limits?",
        "BMC_FAN_FAILURE": "Is a fan physically failed or is the BMC sensor reporting stale data?",
    }
    for code in codes:
        if code in questions:
            return questions[code]
    return "What additional evidence would confirm whether the current scheduling label is appropriate?"


def _summarize(values: list[str | None]) -> str | None:
    present = sorted(set(value for value in values if value))
    if not present:
        return None
    return present[0] if len(present) == 1 else "mixed"


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _version_matches(actual: str | None, expected: str | None) -> bool:
    if actual is None or expected is None:
        return False
    expected = expected.strip()
    if expected.startswith(">="):
        return _version_tuple(actual) >= _version_tuple(expected[2:].strip())
    if expected.startswith("=="):
        return actual == expected[2:].strip()
    return actual == expected


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers[:4])
