from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


QualificationStatus = Literal["PASS", "REVIEW", "INFERENCE_ONLY", "AVOID_MULTINODE", "QUARANTINE"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
RecommendedState = Literal["KEEP", "REVIEW", "DRAIN_REVIEW", "QUARANTINE_REVIEW"]
ReadinessLane = Literal[
    "MULTINODE_READY",
    "SINGLE_NODE_READY",
    "INFERENCE_ONLY",
    "AVOID_MULTINODE",
    "REVIEW_REQUIRED",
    "QUARANTINE_REVIEW",
]


class NcclSample(BaseModel):
    message_size_bytes: int
    algbw_gbps: float | None = None
    busbw_gbps: float | None = None
    wrong_count: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)


class NcclResult(BaseModel):
    present: bool = False
    parsed: bool = False
    samples: list[NcclSample] = Field(default_factory=list)
    status: str = "MISSING"
    best_bandwidth_gbps: float | None = None
    p50_bandwidth_gbps: float | None = None
    p10_bandwidth_gbps: float | None = None
    p90_bandwidth_gbps: float | None = None
    max_message_size_bytes: int | None = None
    timeout: bool = False
    correctness_error: bool = False
    wrong_count_total: int = 0
    warning_excerpts: list[str] = Field(default_factory=list)
    error_excerpts: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class PairwiseNcclRecord(BaseModel):
    test_id: str
    nodes: list[str]
    gpus_per_node: int | None = None
    message_size_bytes: int | None = None
    busbw_gbps: float | None = None
    algbw_gbps: float | None = None
    duration_ms: float | None = None
    status: str = "UNKNOWN"
    timeout: bool = False
    wrong_count: int = 0
    stderr_excerpt: str | None = None


class PairwiseNcclResult(BaseModel):
    present: bool = False
    parsed: bool = False
    records: list[PairwiseNcclRecord] = Field(default_factory=list)
    status: str = "MISSING"
    weak_peer_count: int = 0
    timeout_count: int = 0
    min_busbw_gbps: float | None = None
    p50_busbw_gbps: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TopologyMatrix(BaseModel):
    present: bool = False
    parsed: bool = False
    gpu_names: list[str] = Field(default_factory=list)
    nic_names: list[str] = Field(default_factory=list)
    gpu_gpu_path_counts: dict[str, int] = Field(default_factory=dict)
    gpu_nic_path_counts: dict[str, int] = Field(default_factory=dict)
    nvlink_path_count: int = 0
    weak_gpu_path_count: int = 0
    review_gpu_path_count: int = 0
    p2p_nvlink_missing_count: int = 0
    cpu_affinity: dict[str, str] = Field(default_factory=dict)
    numa_affinity: dict[str, str] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NvidiaSmiGpuInfo(BaseModel):
    uuid: str | None = None
    product_name: str | None = None
    vbios_version: str | None = None
    ecc_mode: str | None = None
    retired_pages: int = 0
    temperature_celsius: float | None = None
    power_draw_watts: float | None = None
    clocks_throttle_reasons: list[str] = Field(default_factory=list)
    mig_mode: str | None = None
    serial: str | None = None


class NvidiaSmiQueryResult(BaseModel):
    present: bool = False
    parsed: bool = False
    driver_version: str | None = None
    cuda_version: str | None = None
    gpus: list[NvidiaSmiGpuInfo] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BmcSensor(BaseModel):
    sensor_name: str
    sensor_type: str = "unknown"
    reading: float | None = None
    units: str | None = None
    status_state: str | None = None
    status_health: str | None = None
    upper_warning: float | None = None
    upper_critical: float | None = None
    lower_warning: float | None = None
    lower_critical: float | None = None
    serial: str | None = None


class BmcSnapshot(BaseModel):
    present: bool = False
    parsed: bool = False
    sensors: list[BmcSensor] = Field(default_factory=list)
    warning_count: int = 0
    critical_count: int = 0
    fan_failure_count: int = 0
    temp_max_celsius: float | None = None
    power_warning_count: int = 0
    power_critical_count: int = 0
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ExpectedInventory(BaseModel):
    gpu_count: int | None = None
    gpu_product_name_regex: str | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    vbios_consistent_within_node: bool | None = True
    mig_mode: str | None = None
    ecc_mode: str | None = None


class NodeInventoryEntry(BaseModel):
    name: str
    rack: str | None = None
    rack_position: str | None = None
    switch_group: str | None = None
    fabric_group: str | None = None
    expected_role: list[str] = Field(default_factory=list)
    expected_gpu_count: int | None = None
    expected_nic_count: int | None = None
    expected_features: list[str] = Field(default_factory=list)
    maintenance_window: str | None = None


class NodeInventory(BaseModel):
    cluster_id: str | None = None
    rack_id: str | None = None
    expected: ExpectedInventory = Field(default_factory=ExpectedInventory)
    nodes: list[NodeInventoryEntry] = Field(default_factory=list)

    def by_name(self) -> dict[str, NodeInventoryEntry]:
        return {node.name: node for node in self.nodes}


class EvidencePolicy(BaseModel):
    require_nccl_single_node: bool = True
    require_topo: bool = True
    require_nvidia_smi_query: bool = True
    require_bmc_snapshot: bool = False
    require_pairwise_nccl_for_multinode_label: bool = True
    require_node_inventory: bool = False


class NcclPolicy(BaseModel):
    use_metric: str = "busbw_gbps"
    peer_median_warning_pct: float = 75
    peer_median_fail_pct: float = 50
    min_single_node_busbw_gbps: float | None = None
    min_pairwise_busbw_gbps: float | None = None
    timeout_is_quarantine: bool = True
    correctness_error_is_quarantine: bool = True
    wrong_count_is_quarantine: bool = True
    min_message_size_bytes_for_scoring: int = 67108864


class TopologyPolicy(BaseModel):
    require_nvlink_for_multinode_training: bool = False
    weak_gpu_gpu_paths: list[str] = Field(default_factory=lambda: ["SYS", "PHB"])
    review_gpu_gpu_paths: list[str] = Field(default_factory=lambda: ["PXB"])
    weak_if_any_gpu_pair_weak: bool = True
    p2p_nvlink_expected: bool = False


class FirmwarePolicy(BaseModel):
    require_driver_consistency_across_rack: bool = True
    require_vbios_consistency_within_node: bool = True
    driver_mismatch_action: str = "REVIEW"
    vbios_mismatch_action: str = "DRAIN_REVIEW"
    cuda_mismatch_action: str = "REVIEW"


class SensorsPolicy(BaseModel):
    health_warning_action: str = "REVIEW"
    health_critical_action: str = "QUARANTINE"
    fan_failure_action: str = "QUARANTINE"
    temp_warning_celsius: float = 80
    temp_critical_celsius: float = 90
    power_warning_action: str = "REVIEW"
    power_critical_action: str = "QUARANTINE"


class LabelsPolicy(BaseModel):
    pass_label: str = "rackq_pass"
    review_label: str = "rackq_review"
    quarantine_label: str = "rackq_quarantine"
    inference_ok_label: str = "gpu_inference_ok"
    single_node_training_ok_label: str = "gpu_training_single_node_ok"
    multi_node_training_ok_label: str = "gpu_training_multinode_ok"
    avoid_multinode_label: str = "gpu_avoid_multinode"
    weak_link_label: str = "gpu_link_weak"
    firmware_review_label: str = "gpu_fw_review"
    sensor_review_label: str = "gpu_sensor_review"
    do_not_schedule_label: str = "gpu_do_not_schedule"
    allow_inference_when_quarantined: bool = False
    allow_pass_with_warnings: bool = False


class QuarantinePolicy(BaseModel):
    drain_on_correctness_error: bool = True
    drain_on_timeout: bool = True
    drain_on_sensor_critical: bool = True
    drain_on_missing_gpu: bool = True
    drain_on_vbios_mismatch: bool = False


class QualificationPolicy(BaseModel):
    policy_id: str = "default"
    evidence: EvidencePolicy = Field(default_factory=EvidencePolicy)
    nccl: NcclPolicy = Field(default_factory=NcclPolicy)
    topology: TopologyPolicy = Field(default_factory=TopologyPolicy)
    firmware: FirmwarePolicy = Field(default_factory=FirmwarePolicy)
    sensors: SensorsPolicy = Field(default_factory=SensorsPolicy)
    labels: LabelsPolicy = Field(default_factory=LabelsPolicy)
    quarantine: QuarantinePolicy = Field(default_factory=QuarantinePolicy)


class NodeEvidence(BaseModel):
    node_name: str
    path: Path
    source_files: dict[str, str] = Field(default_factory=dict)
    nccl_single: NcclResult = Field(default_factory=NcclResult)
    pairwise_nccl: PairwiseNcclResult = Field(default_factory=PairwiseNcclResult)
    topology: TopologyMatrix = Field(default_factory=TopologyMatrix)
    nvidia_smi_query: NvidiaSmiQueryResult = Field(default_factory=NvidiaSmiQueryResult)
    bmc_snapshot: BmcSnapshot = Field(default_factory=BmcSnapshot)
    warnings: list[str] = Field(default_factory=list)


class DerivedNodeFeatures(BaseModel):
    node_name: str
    evidence_present: list[str] = Field(default_factory=list)
    gpu_count: int | None = None
    expected_gpu_count: int | None = None
    gpu_count_ok: bool | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    vbios_versions: list[str] = Field(default_factory=list)
    vbios_consistent_within_node: bool | None = None
    mig_mode_summary: str | None = None
    ecc_mode_summary: str | None = None
    single_node_nccl_status: str = "MISSING"
    single_node_busbw_best_gbps: float | None = None
    single_node_busbw_p50_gbps: float | None = None
    single_node_busbw_vs_peer_median_pct: float | None = None
    pairwise_nccl_status: str = "MISSING"
    pairwise_weak_peer_count: int = 0
    pairwise_timeout_count: int = 0
    pairwise_min_busbw_gbps: float | None = None
    pairwise_p50_busbw_gbps: float | None = None
    weak_topology_path_count: int = 0
    review_topology_path_count: int = 0
    p2p_nvlink_missing_count: int = 0
    bmc_warning_count: int = 0
    bmc_critical_count: int = 0
    fan_failure_count: int = 0
    temp_max_celsius: float | None = None
    firmware_mismatch_count: int = 0
    confidence: Confidence = "LOW"
    reason_codes: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggested_operator_question: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class QualificationResult(BaseModel):
    features: DerivedNodeFeatures
    qualification_status: QualificationStatus
    slurm_features: list[str] = Field(default_factory=list)
    recommended_state: RecommendedState = "REVIEW"
    recommended_partition_hint: str = "review"
    policy_decisions: list[dict[str, Any]] = Field(default_factory=list)


class SlurmLabelRow(BaseModel):
    node_name: str
    qualification_status: str
    confidence: str
    slurm_features: str
    recommended_state: str
    recommended_partition_hint: str
    gpu_count: int | None
    expected_gpu_count: int | None
    single_node_busbw_p50_gbps: float | None
    single_node_busbw_vs_peer_median_pct: float | None
    pairwise_p50_busbw_gbps: float | None
    pairwise_weak_peer_count: int
    weak_topology_path_count: int
    bmc_warning_count: int
    bmc_critical_count: int
    firmware_mismatch_count: int
    reason_codes: str
    blockers: str
    warnings: str
    suggested_operator_question: str
    source_evidence: str


class QuarantineRow(BaseModel):
    node_name: str
    recommendation: str
    severity: str
    confidence: str
    primary_reason: str
    reason_codes: str
    blockers: str
    suggested_slurm_state: str
    suggested_drain_reason: str
    safe_for_inference_candidate: bool
    avoid_multinode_candidate: bool
    operator_action: str
    suggested_operator_question: str
    source_evidence: str


class Summary(BaseModel):
    cluster_id: str | None
    rack_id: str | None
    generated_at: str
    policy_id: str
    mode: str = "REVIEW_ONLY"
    input: dict[str, int]
    qualification: dict[str, int]
    labels: dict[str, int]
    blockers: dict[str, int]
    warnings: list[str]
    top_operator_questions: list[str]
    business_impact: dict[str, Any] = Field(default_factory=dict)
    readiness: dict[str, int] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    action_queue_counts: dict[str, int] = Field(default_factory=dict)
    outputs: dict[str, str]


class BusinessAssumptions(BaseModel):
    gpus_per_node: int | None = None
    hours_at_risk: float | None = None
    accelerator_hour_value: float | None = None
    release_goal: str = "multinode_training"


class ReviewQueueRow(BaseModel):
    priority: str
    node_name: str
    readiness_lane: str
    recommended_state: str
    primary_reason: str
    operator_action: str
    business_risk: str
    confidence: str
    blocking_evidence: str
    next_question: str
    source_evidence: str
