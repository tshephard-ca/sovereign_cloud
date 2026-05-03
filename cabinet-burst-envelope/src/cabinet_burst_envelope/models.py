from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import (
    ACTION_QUEUE_SCHEMA_VERSION,
    ENVELOPE_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    REVIEW_LANE_SCHEMA_VERSION,
    SCENARIO_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    __version__,
)


Risk = Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
EnvelopeStatus = Literal[
    "READY_FOR_REVIEW",
    "REVIEW_REQUIRED",
    "DO_NOT_EXPAND",
    "INSUFFICIENT_DATA",
]
LimitingFactor = Literal["ELECTRICAL", "THERMAL", "BOTH", "DATA_QUALITY", "UNKNOWN"]
ThermalModelStatus = Literal["USABLE", "UNUSABLE"]
ReviewLaneName = Literal[
    "READY_FOR_FACILITY_REVIEW",
    "NEEDS_REMEDIATION",
    "STOP_EXPANSION_DISCUSSION",
    "COLLECT_EVIDENCE",
]
ActionPriority = Literal["HIGH", "MEDIUM", "LOW"]
RedundancyMode = Literal[
    "SINGLE",
    "A_B_SHARED",
    "A_B_REDUNDANT",
    "A_B_NON_REDUNDANT",
    "UNKNOWN",
]


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PowerReading(StrictBaseModel):
    timestamp: datetime
    cabinet_id: str
    reading_kw: float
    feed_id: str | None = None
    pdu_id: str | None = None
    reading_scope: str = "unknown"
    source: str | None = None
    phase: str | None = None
    circuit_id: str | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    apparent_power_kva: float | None = None
    power_factor: float | None = None
    outlet_id: str | None = None
    reading_quality: str = "good"
    source_row_id: str | None = None
    source_row_number: int | None = None
    timezone_unknown: bool = False


class TemperatureReading(StrictBaseModel):
    timestamp: datetime
    cabinet_id: str
    sensor_id: str
    inlet_temp_c: float
    position: str = "unknown"
    height: str = "unknown"
    source: str | None = None
    sensor_role: str = "unknown"
    reading_quality: str = "good"
    humidity_pct: float | None = None
    dewpoint_c: float | None = None
    source_row_id: str | None = None
    source_row_number: int | None = None
    timezone_unknown: bool = False


class FeedLimit(StrictBaseModel):
    feed_id: str
    usable_sustained_kw: float | None = None
    trip_risk_kw: float | None = None


class ElectricalProfile(StrictBaseModel):
    usable_sustained_kw: float | None = None
    usable_burst_kw: float | None = None
    trip_risk_kw: float | None = None
    redundancy_mode: RedundancyMode = "UNKNOWN"
    require_single_feed_survival: bool = False
    feed_limits: list[FeedLimit] = Field(default_factory=list)


class ThermalProfile(StrictBaseModel):
    inlet_warning_c: float | None = None
    inlet_critical_c: float | None = None
    require_top_middle_bottom: bool = False
    max_thermal_extrapolation_kw: float | None = None
    thermal_model_required_for_burst: bool = False


class GuardbandProfile(StrictBaseModel):
    power_headroom_pct: float | None = None
    min_power_headroom_kw: float | None = None
    temp_headroom_c: float | None = None
    sustained_window_minutes: int | None = None
    burst_window_minutes: int | None = None
    max_burst_duration_minutes: int | None = None


class SalesPolicy(StrictBaseModel):
    allow_sales_guardrail: bool = True
    require_ops_review_above_kw: float | None = None
    require_facility_review_above_kw: float | None = None
    wording: str = "conservative"


class CabinetProfile(StrictBaseModel):
    cabinet_id: str
    display_name: str | None = None
    site_policy_id: str | None = None
    workload_label: str | None = None
    electrical: ElectricalProfile = Field(default_factory=ElectricalProfile)
    thermal: ThermalProfile = Field(default_factory=ThermalProfile)
    guardbands: GuardbandProfile = Field(default_factory=GuardbandProfile)
    sales_policy: SalesPolicy = Field(default_factory=SalesPolicy)


class TimeBucket(StrictBaseModel):
    timestamp: datetime
    cabinet_id: str
    cabinet_power_kw: float | None = None
    feed_power_kw: dict[str, float] = Field(default_factory=dict)
    max_inlet_temp_c: float | None = None
    top_inlet_temp_c: float | None = None
    middle_inlet_temp_c: float | None = None
    bottom_inlet_temp_c: float | None = None
    power_bucket_quality: str = "missing"
    temperature_bucket_quality: str = "missing"
    aligned_bucket_quality: str = "missing"
    notes: list[str] = Field(default_factory=list)


class CoverageStats(StrictBaseModel):
    expected_buckets: int
    power_buckets: int
    temperature_buckets: int
    aligned_buckets: int
    power_coverage_pct: float
    temperature_coverage_pct: float
    aligned_coverage_pct: float
    longest_power_gap_minutes: int
    longest_temperature_gap_minutes: int


class AlignmentResult(StrictBaseModel):
    cabinet_id: str
    window_start: datetime
    window_end: datetime
    window_days: int
    bucket_minutes: int
    buckets: list[TimeBucket]
    coverage: CoverageStats
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class PowerStats(StrictBaseModel):
    observed_power_min_kw: float | None = None
    observed_power_p50_kw: float | None = None
    observed_power_p95_kw: float | None = None
    observed_power_p99_kw: float | None = None
    observed_power_max_kw: float | None = None
    observed_sustained_p95_kw: float | None = None
    observed_short_burst_p99_kw: float | None = None
    observed_short_burst_max_kw: float | None = None
    observed_power_ramp_max_kw_per_min: float | None = None
    feed_imbalance_pct: float | None = None
    feed_a_p95_kw: float | None = None
    feed_b_p95_kw: float | None = None


class TemperatureStats(StrictBaseModel):
    observed_inlet_min_c: float | None = None
    observed_inlet_p50_c: float | None = None
    observed_inlet_p95_c: float | None = None
    observed_inlet_p99_c: float | None = None
    observed_inlet_max_c: float | None = None
    observed_top_inlet_max_c: float | None = None
    observed_middle_inlet_max_c: float | None = None
    observed_bottom_inlet_max_c: float | None = None
    observed_temp_ramp_max_c_per_min: float | None = None
    hotspot_delta_top_bottom_c: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class ThermalModelResult(StrictBaseModel):
    thermal_model_status: ThermalModelStatus
    slope_c_per_kw: float | None = None
    intercept_c: float | None = None
    r_squared: float | None = None
    best_lag_minutes: int = 0
    best_lag_r_squared: float | None = None
    sample_count: int = 0
    power_range_kw: float | None = None
    temp_range_c: float | None = None
    predicted_warning_power_kw: float | None = None
    predicted_critical_power_kw: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ElectricalEnvelope(StrictBaseModel):
    electrical_sustained_limit_kw: float | None = None
    electrical_burst_limit_kw: float | None = None
    trip_risk_threshold_kw: float | None = None
    power_guardband_kw: float | None = None
    electrical_guardrail_sustained_kw: float | None = None
    electrical_guardrail_burst_kw: float | None = None
    electrical_headroom_sustained_kw: float | None = None
    electrical_headroom_burst_kw: float | None = None
    electrical_risk: Risk = "UNKNOWN"
    trip_risk: Risk = "UNKNOWN"
    feed_imbalance_pct: float | None = None
    electrical_reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class ThermalEnvelope(StrictBaseModel):
    thermal_model_status: ThermalModelStatus
    thermal_slope_c_per_kw: float | None = None
    thermal_model_r2: float | None = None
    best_lag_minutes: int = 0
    best_lag_r_squared: float | None = None
    predicted_warning_power_kw: float | None = None
    predicted_critical_power_kw: float | None = None
    thermal_guardrail_sustained_kw: float | None = None
    thermal_guardrail_burst_kw: float | None = None
    thermal_risk_threshold_kw: float | None = None
    thermal_headroom_c: float | None = None
    thermal_risk: Risk = "UNKNOWN"
    thermal_reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class SalesOpsGuardrail(StrictBaseModel):
    status: EnvelopeStatus
    text: str
    recommended_next_step: str


class ActionItem(StrictBaseModel):
    action_id: str
    title: str
    owner: str
    priority: ActionPriority
    reason_codes: list[str] = Field(default_factory=list)
    evidence_needed: list[str] = Field(default_factory=list)
    business_impact: str
    completion_signal: str


class ReviewLaneDecision(StrictBaseModel):
    schema_version: str = REVIEW_LANE_SCHEMA_VERSION
    tool_version: str = __version__
    cabinet_id: str
    lane: ReviewLaneName
    envelope_status: EnvelopeStatus
    business_action: str
    decision_owner: str
    primary_constraint: str
    evidence_gate: str
    remediation_categories: list[str] = Field(default_factory=list)
    next_actions: list[ActionItem] = Field(default_factory=list)
    conversation_boundary: str
    why_this_matters: str
    decision_trace: dict[str, Any] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class ActionQueue(StrictBaseModel):
    schema_version: str = ACTION_QUEUE_SCHEMA_VERSION
    tool_version: str = __version__
    cabinet_id: str
    review_lane: ReviewLaneName
    actions: list[ActionItem] = Field(default_factory=list)


class CabinetEnvelope(StrictBaseModel):
    schema_version: str = ENVELOPE_SCHEMA_VERSION
    tool_version: str = __version__
    cabinet_id: str
    generated_at: datetime
    window: dict[str, Any]
    envelope_status: EnvelopeStatus
    confidence: Confidence
    recommended_sustained_kw: float | None = None
    recommended_short_burst_kw: float | None = None
    max_burst_duration_minutes: int | None = None
    trip_risk_threshold_kw: float | None = None
    thermal_risk_threshold_kw: float | None = None
    limiting_factor: LimitingFactor = "UNKNOWN"
    observed_power: dict[str, Any] = Field(default_factory=dict)
    observed_temperature: dict[str, Any] = Field(default_factory=dict)
    electrical: dict[str, Any] = Field(default_factory=dict)
    thermal: dict[str, Any] = Field(default_factory=dict)
    evidence_quality: dict[str, Any] = Field(default_factory=dict)
    review_lane: dict[str, Any] = Field(default_factory=dict)
    sales_ops_guardrail: SalesOpsGuardrail
    reason_codes: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class Summary(StrictBaseModel):
    schema_version: str = SUMMARY_SCHEMA_VERSION
    tool_version: str = __version__
    cabinet_id: str
    envelope_status: EnvelopeStatus
    confidence: Confidence
    input: dict[str, Any]
    review_lane: dict[str, Any] = Field(default_factory=dict)
    recommendation: dict[str, Any]
    risk: dict[str, Any]
    reason_code_counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    action_queue: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_questions: list[str] = Field(default_factory=list)


class ParseResult(StrictBaseModel):
    rows: list[Any] = Field(default_factory=list)
    input_rows: int = 0
    cabinet_ids: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class EvidenceManifest(StrictBaseModel):
    schema_version: str = MANIFEST_SCHEMA_VERSION
    tool_version: str = __version__
    generated_at: datetime
    cabinet_id: str
    bundle_type: str
    files: dict[str, str] = Field(default_factory=dict)
    input_fingerprints: dict[str, str] = Field(default_factory=dict)
    envelope_status: EnvelopeStatus | None = None
    confidence: Confidence | None = None
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class ScenarioManifest(StrictBaseModel):
    schema_version: str = SCENARIO_SCHEMA_VERSION
    tool_version: str = __version__
    scenario: str
    cabinet_id: str
    generated_at: datetime
    days: int
    bucket_minutes: int
    seed: int
    files: dict[str, str] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    controls: dict[str, Any] = Field(default_factory=dict)
