from __future__ import annotations

from .classify_processes import ProcessClassification
from .features import worst_risk
from .models import (
    CandidateDataMount,
    EnhancedStorageRequirement,
    EvidenceGraph,
    FitResult,
    RequirementDimension,
    StorageBehaviorFingerprint,
)


def _evidence_ids(graph: EvidenceGraph, *kinds: str) -> list[str]:
    wanted = set(kinds)
    return [obs.id for obs in graph.observations if obs.kind in wanted]


def _dimension(value, confidence: str, graph: EvidenceGraph, *kinds: str, notes: list[str] | None = None):
    return RequirementDimension(
        value=value,
        confidence=confidence,
        evidence_ids=_evidence_ids(graph, *kinds),
        notes=notes or [],
    )


def build_behavior_fingerprint(
    *,
    candidates: list[CandidateDataMount],
    process_info: ProcessClassification,
    graph: EvidenceGraph,
    fit_result: FitResult,
) -> StorageBehaviorFingerprint:
    shared = fit_result.required_access_mode == "ReadWriteMany"
    root_only = "ROOT_ONLY_STORAGE_VIEW" in fit_result.reason_codes
    capacity = worst_risk([candidate.capacity_risk for candidate in candidates])
    latency = fit_result.latency_risk

    writer_topology = "multi_writer_or_shared_namespace_likely" if shared else "single_writer_likely"
    if process_info.file_server_processes and shared:
        writer_topology = "multi_writer_possible"
    elif process_info.file_server_processes:
        writer_topology = "unknown_file_serving_pattern"

    sync_write = "likely" if process_info.database_processes else "possible" if process_info.stateful_processes else "unknown"
    latency_sensitivity = "high" if latency == "HIGH" else "medium" if latency == "MEDIUM" else "unknown"
    if process_info.database_processes and latency in {"LOW", "UNKNOWN"}:
        latency_sensitivity = "possible"

    evidence_quality = "high"
    if fit_result.confidence == "LOW":
        evidence_quality = "low"
    elif fit_result.confidence == "MEDIUM" or root_only:
        evidence_quality = "medium"

    return StorageBehaviorFingerprint(
        shared_namespace_dependency=_dimension(
            shared,
            "HIGH" if shared else "MEDIUM",
            graph,
            "filesystem.shared_or_network",
            notes=[] if shared else ["No candidate data mount used a known shared filesystem type."],
        ),
        writer_topology=_dimension(
            writer_topology,
            "MEDIUM" if process_info.file_server_processes or shared else "LOW",
            graph,
            "filesystem.shared_or_network",
            "process.file_server",
        ),
        file_locking_risk=_dimension(
            "possible" if shared or process_info.file_server_processes else "unknown",
            "LOW" if not shared else "MEDIUM",
            graph,
            "filesystem.shared_or_network",
            "process.file_server",
        ),
        sync_write_sensitivity=_dimension(
            sync_write,
            "MEDIUM" if process_info.database_processes or process_info.stateful_processes else "LOW",
            graph,
            "process.database_like",
            "process.stateful_service",
        ),
        latency_sensitivity=_dimension(
            latency_sensitivity,
            "MEDIUM" if latency in {"MEDIUM", "HIGH"} else "LOW",
            graph,
            "iostat.latency_risk",
            "process.database_like",
            "process.stateful_service",
        ),
        throughput_sensitivity=_dimension(
            "unknown",
            "LOW",
            graph,
            notes=["The MVP evidence set does not include enough throughput history to infer sustained throughput requirements."],
        ),
        capacity_growth_risk=_dimension(
            capacity.lower() if capacity != "UNKNOWN" else "unknown",
            "MEDIUM" if capacity in {"MEDIUM", "HIGH"} else "LOW",
            graph,
            "mount.candidate_data",
        ),
        inode_pressure=_dimension(
            "unknown",
            "LOW",
            graph,
            notes=["Inode pressure requires inode df or filesystem metadata evidence."],
        ),
        raw_block_likelihood=_dimension(
            "required" if process_info.raw_block_required else "hint" if process_info.raw_block_hint else "unlikely",
            "HIGH" if process_info.raw_block_required else "LOW",
            graph,
            "process.raw_device_reference",
        ),
        expansion_need=_dimension(
            capacity in {"MEDIUM", "HIGH"},
            "MEDIUM" if capacity in {"MEDIUM", "HIGH"} else "LOW",
            graph,
            "mount.candidate_data",
        ),
        snapshot_consistency_need=_dimension(
            "possible" if process_info.database_processes or process_info.stateful_processes else "unknown",
            "LOW",
            graph,
            "process.database_like",
            "process.stateful_service",
            notes=["Snapshot support is treated as a preference unless the storage profile or policy pack makes it explicit."],
        ),
        topology_sensitivity=_dimension(
            "unknown",
            "LOW",
            graph,
            notes=["Node, zone, and rescheduling constraints are not visible in the current VM evidence."],
        ),
        permission_assumption_risk=_dimension(
            "unknown",
            "LOW",
            graph,
            notes=["UID/GID, SELinux, and fsGroup compatibility are outside the current storage evidence set."],
        ),
        evidence_quality=_dimension(evidence_quality, fit_result.confidence, graph),
    )


def build_enhanced_requirement(
    *,
    fit_result: FitResult,
    fingerprint: StorageBehaviorFingerprint,
) -> EnhancedStorageRequirement:
    hard: list[str] = [
        f"access_mode={fit_result.required_access_mode}",
        f"volume_mode={fit_result.required_volume_mode}",
    ]
    soft: list[str] = []
    unresolved: list[str] = []

    if fit_result.preferred_storage_kind != "unknown":
        hard.append(f"storage_kind={fit_result.preferred_storage_kind}")
    if fit_result.storage_request_gib is not None:
        hard.append(f"size_gib>={fit_result.storage_request_gib}")
    if fit_result.required_access_mode == "ReadWriteMany":
        hard.append("shared_namespace_filesystem=true")
    if fit_result.required_volume_mode == "Block":
        hard.append("raw_block_volume=true")
    required_tier = "standard"
    if "LOW_LATENCY_STORAGE_RECOMMENDED" in fit_result.reason_codes:
        required_tier = "low_latency"
    elif "FAST_STORAGE_RECOMMENDED" in fit_result.reason_codes:
        required_tier = "fast"
    if required_tier != "standard":
        hard.append(f"performance_tier>={required_tier}")
    if fingerprint.expansion_need.value:
        soft.append("supports_expansion_preferred=true")
    if fingerprint.snapshot_consistency_need.value == "possible":
        soft.append("supports_snapshots_preferred=true")
    if fingerprint.file_locking_risk.value != "unknown":
        unresolved.append("file_locking_semantics")
    if fingerprint.topology_sensitivity.value == "unknown":
        unresolved.append("node_zone_topology")
    if fingerprint.permission_assumption_risk.value == "unknown":
        unresolved.append("filesystem_identity_and_permissions")
    if fingerprint.throughput_sensitivity.value == "unknown":
        unresolved.append("sustained_throughput")

    return EnhancedStorageRequirement(
        required_access_mode=fit_result.required_access_mode,
        required_volume_mode=fit_result.required_volume_mode,
        preferred_storage_kind=fit_result.preferred_storage_kind,
        storage_request_gib=fit_result.storage_request_gib,
        required_performance_tier=required_tier,
        hard_requirements=hard,
        soft_preferences=soft,
        unresolved_requirements=unresolved,
    )
