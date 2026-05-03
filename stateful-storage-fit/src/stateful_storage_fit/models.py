from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DfFilesystem(BaseModel):
    filesystem: str
    fs_type: Optional[str] = None
    size_bytes: Optional[int] = None
    used_bytes: Optional[int] = None
    available_bytes: Optional[int] = None
    capacity_pct: Optional[float] = None
    mount_path: str
    raw: str = ""


class MountEntry(BaseModel):
    source: str
    mount_path: str
    fs_type: str
    options: list[str] = Field(default_factory=list)
    raw: str = ""


class FstabEntry(BaseModel):
    source: str
    mount_path: str
    fs_type: str
    options: list[str] = Field(default_factory=list)
    dump: Optional[str] = None
    passno: Optional[str] = None
    raw: str = ""


class IoDeviceSample(BaseModel):
    device: str
    await_ms: Optional[float] = None
    r_await_ms: Optional[float] = None
    w_await_ms: Optional[float] = None
    util_pct: Optional[float] = None
    queue_depth: Optional[float] = None
    samples_count: int = 0
    max_await_ms: Optional[float] = None
    max_util_pct: Optional[float] = None
    raw_metrics: dict[str, float] = Field(default_factory=dict)


class ProcessEntry(BaseModel):
    pid: Optional[int] = None
    command: str
    args: Optional[str] = None
    raw: str = ""


class StorageClassProfile(BaseModel):
    name: str
    display_name: Optional[str] = None
    access_modes: list[str]
    volume_modes: list[str]
    storage_kind: str
    performance_tier: str
    max_size_gib: Optional[int] = None
    supports_expansion: bool = False
    supports_snapshots: bool = False


class StorageProfile(BaseModel):
    storage_classes: list[StorageClassProfile]
    performance_tiers: dict[str, int]


class CandidateDataMount(BaseModel):
    mount_path: str
    source: str
    fs_type: str
    used_gib: Optional[float] = None
    available_gib: Optional[float] = None
    capacity_used_pct: Optional[float] = None
    is_candidate_data_mount: bool = True
    data_mount_reason: str
    inferred_role: str = "general_data"
    device_from_iostat: Optional[str] = None
    await_ms: Optional[float] = None
    util_pct: Optional[float] = None
    capacity_risk: str = "UNKNOWN"
    latency_risk: str = "UNKNOWN"
    candidate_score: float = 0.0
    candidate_score_reasons: list[str] = Field(default_factory=list)
    ownership_confidence: str = "LOW"
    false_positive_risk: str = "MEDIUM"
    notes: list[str] = Field(default_factory=list)


class StorageRequirement(BaseModel):
    required_access_mode: str = "ReadWriteOnce"
    required_volume_mode: str = "Filesystem"
    preferred_storage_kind: str = "unknown"
    storage_request_gib: Optional[int] = None
    required_performance_tier: str = "standard"


class RejectedStorageClass(BaseModel):
    name: str
    reasons: list[str]


class FitResult(BaseModel):
    fit_status: str
    recommended_storage_class: Optional[str] = None
    required_access_mode: str
    required_volume_mode: str
    preferred_storage_kind: str
    storage_request_gib: Optional[int] = None
    capacity_risk: str
    latency_risk: str
    confidence: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    reason_text: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    matched_storage_classes: list[str] = Field(default_factory=list)
    rejected_storage_classes: list[RejectedStorageClass] = Field(default_factory=list)
    analysis: Optional[dict[str, Any]] = None


class EvidenceObservation(BaseModel):
    id: str
    kind: str
    source: str
    subject: str
    value: Any = None
    confidence: str = "MEDIUM"
    supports: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EvidenceInference(BaseModel):
    id: str
    kind: str
    statement: str
    confidence: str = "MEDIUM"
    evidence_ids: list[str] = Field(default_factory=list)
    requirement_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EvidenceGraph(BaseModel):
    schema_version: str = "1.0"
    observations: list[EvidenceObservation] = Field(default_factory=list)
    inferences: list[EvidenceInference] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)


class RequirementDimension(BaseModel):
    value: Any = None
    confidence: str = "LOW"
    evidence_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StorageBehaviorFingerprint(BaseModel):
    schema_version: str = "1.0"
    shared_namespace_dependency: RequirementDimension = Field(default_factory=RequirementDimension)
    writer_topology: RequirementDimension = Field(default_factory=RequirementDimension)
    file_locking_risk: RequirementDimension = Field(default_factory=RequirementDimension)
    sync_write_sensitivity: RequirementDimension = Field(default_factory=RequirementDimension)
    latency_sensitivity: RequirementDimension = Field(default_factory=RequirementDimension)
    throughput_sensitivity: RequirementDimension = Field(default_factory=RequirementDimension)
    capacity_growth_risk: RequirementDimension = Field(default_factory=RequirementDimension)
    inode_pressure: RequirementDimension = Field(default_factory=RequirementDimension)
    raw_block_likelihood: RequirementDimension = Field(default_factory=RequirementDimension)
    expansion_need: RequirementDimension = Field(default_factory=RequirementDimension)
    snapshot_consistency_need: RequirementDimension = Field(default_factory=RequirementDimension)
    topology_sensitivity: RequirementDimension = Field(default_factory=RequirementDimension)
    permission_assumption_risk: RequirementDimension = Field(default_factory=RequirementDimension)
    evidence_quality: RequirementDimension = Field(default_factory=RequirementDimension)


class EnhancedStorageRequirement(BaseModel):
    required_access_mode: str
    required_volume_mode: str
    preferred_storage_kind: str
    storage_request_gib: Optional[int] = None
    required_performance_tier: str = "standard"
    hard_requirements: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    unresolved_requirements: list[str] = Field(default_factory=list)


class CompatibilityConstraint(BaseModel):
    id: str
    level: str
    description: str
    required: Any = None
    actual: Any = None
    satisfied: bool = False
    reason_code: Optional[str] = None


class StorageClassCompatibility(BaseModel):
    storage_class: str
    status: str
    hard_failures: list[CompatibilityConstraint] = Field(default_factory=list)
    soft_warnings: list[CompatibilityConstraint] = Field(default_factory=list)
    satisfied_constraints: list[CompatibilityConstraint] = Field(default_factory=list)
    counterfactuals: list[str] = Field(default_factory=list)
    score: int = 0


class EvidenceQuestion(BaseModel):
    id: str
    priority: str
    question: str
    why_it_matters: str
    would_change: list[str] = Field(default_factory=list)
    related_reason_codes: list[str] = Field(default_factory=list)
    suggested_local_evidence: list[str] = Field(default_factory=list)


class DeepFitAnalysis(BaseModel):
    schema_version: str = "1.0"
    engine_version: str = "storage-inference-v1"
    evidence_graph: EvidenceGraph
    behavior_fingerprint: StorageBehaviorFingerprint
    enhanced_requirement: EnhancedStorageRequirement
    compatibility: list[StorageClassCompatibility] = Field(default_factory=list)
    evidence_questions: list[EvidenceQuestion] = Field(default_factory=list)
    decision_drivers: list[str] = Field(default_factory=list)


class PolicyPack(BaseModel):
    name: str
    version: str
    workload_family: str
    description: Optional[str] = None
    threshold_overrides: dict[str, Any] = Field(default_factory=dict)
    required_evidence: list[str] = Field(default_factory=list)
    reason_text: dict[str, str] = Field(default_factory=dict)


class AnalysisBundle(BaseModel):
    result: FitResult
    candidate_mounts: list[CandidateDataMount] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
