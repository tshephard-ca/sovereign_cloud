from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from .validators import validate_ip_address, validate_ip_or_cidr, validate_port_spec


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AttackClass(StrEnum):
    VOLUMETRIC = "VOLUMETRIC"
    PROTOCOL = "PROTOCOL"
    APPLICATION = "APPLICATION"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class MitigationState(StrEnum):
    DETECTED = "DETECTED"
    ACTIVE = "ACTIVE"
    ESCALATED = "ESCALATED"
    STABLE = "STABLE"
    ENDED = "ENDED"
    UNKNOWN = "UNKNOWN"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class BrownoutMode(StrEnum):
    PROTECT = "PROTECT"
    RESTRICT_TO_TRUSTED = "RESTRICT_TO_TRUSTED"
    RATE_LIMIT = "RATE_LIMIT"
    SHED = "SHED"
    ISOLATE = "ISOLATE"
    NO_ACTION = "NO_ACTION"


class ActionType(StrEnum):
    ALLOW_TRUSTED_SOURCES = "ALLOW_TRUSTED_SOURCES"
    DENY_UNTRUSTED = "DENY_UNTRUSTED"
    RATE_LIMIT = "RATE_LIMIT"
    RATE_LIMIT_UNTRUSTED = "RATE_LIMIT_UNTRUSTED"
    PRIORITIZE = "PRIORITIZE"
    DEPRIORITIZE = "DEPRIORITIZE"
    SHED_LOW_PRIORITY = "SHED_LOW_PRIORITY"
    CHALLENGE = "CHALLENGE"
    TEMPORARY_BLOCK_PORT = "TEMPORARY_BLOCK_PORT"
    TEMPORARY_NULL_ROUTE = "TEMPORARY_NULL_ROUTE"
    MONITOR_ONLY = "MONITOR_ONLY"
    NO_ACTION = "NO_ACTION"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EndpointExposure(StrEnum):
    PUBLIC = "PUBLIC"
    PARTNER_ONLY = "PARTNER_ONLY"
    WORKFORCE_ONLY = "WORKFORCE_ONLY"
    PRIVATE = "PRIVATE"
    MONITORING_ONLY = "MONITORING_ONLY"


class EnforcementPoint(StrEnum):
    NETWORK_EDGE = "NETWORK_EDGE"
    FIREWALL = "FIREWALL"
    ROUTER = "ROUTER"
    WAF = "WAF"
    LOAD_BALANCER = "LOAD_BALANCER"
    SIP_EDGE = "SIP_EDGE"
    VPN_EDGE = "VPN_EDGE"
    MONITORING_ENDPOINT = "MONITORING_ENDPOINT"
    PAYMENT_ENDPOINT = "PAYMENT_ENDPOINT"


class CriticalOperatingPeriod(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str | None = None
    start: str | None = None
    end: str | None = None


class ApprovalMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    named_approver: str | None = None
    role_group: str | None = None
    approval_channel: str | None = None
    approval_expiry_minutes: int | None = None
    emergency_delegation: str | None = None


class RollbackControl(BaseModel):
    model_config = ConfigDict(extra="allow")

    rollback_owner: str | None = None
    escalation_contact: str | None = None
    expected_baseline_state: str | None = None
    verification_steps: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)


class ServiceDependency(BaseModel):
    model_config = ConfigDict(extra="allow")

    service_id: str
    relationship: str = "depends_on"
    notes: str | None = None


class MaintenanceWindow(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    start: str | None = None
    end: str | None = None
    action_guidance: str | None = None


class TrafficBaseline(BaseModel):
    model_config = ConfigDict(extra="allow")

    baseline_bps: int | None = None
    baseline_pps: int | None = None
    normal_bps_low: int | None = None
    normal_bps_high: int | None = None
    normal_pps_low: int | None = None
    normal_pps_high: int | None = None
    seasonal_note: str | None = None


class EventSignals(BaseModel):
    model_config = ConfigDict(extra="allow")

    top_source_countries: list[str] = Field(default_factory=list)
    top_source_asns: list[str] = Field(default_factory=list)
    top_source_prefixes: list[str] = Field(default_factory=list)
    protocol_mix: dict[str, int] = Field(default_factory=dict)
    user_agent_anomalies: bool | None = None
    path_anomalies: list[str] = Field(default_factory=list)
    spoofing_likely: bool = False
    telemetry_source: str | None = None
    collector_type: str | None = None
    sampling_window_seconds: int | None = None
    sample_size: int | None = None
    window_started_at: datetime | None = None
    window_ended_at: datetime | None = None
    evidence_age_seconds: int | None = None
    signal_confidence: Confidence | None = None


class EventTimelineEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    observed_at: datetime
    severity: Severity
    mitigation_state: MitigationState
    summary: str | None = None


class EventTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    ip: str
    protocol: str = "any"
    ports: list[int | str] | None = None
    observed_bps: int | None = None
    observed_pps: int | None = None
    baseline_bps: int | None = None
    baseline_pps: int | None = None

    @field_validator("ip")
    @classmethod
    def valid_ip(cls, value: str) -> str:
        return validate_ip_address(value)

    @field_validator("protocol")
    @classmethod
    def normalize_protocol(cls, value: str) -> str:
        normalized = value.lower()
        if not normalized:
            raise ValueError("protocol must not be empty")
        return normalized

    @field_validator("ports")
    @classmethod
    def valid_ports(cls, value: list[int | str] | None) -> list[int | str] | None:
        if value is None:
            return None
        for port in value:
            validate_port_spec(port)
        return value


class DdosEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    started_at: datetime | None = None
    observed_at: datetime | None = None
    severity: Severity
    attack_class: AttackClass
    mitigation_state: MitigationState
    confidence: Confidence = Confidence.MEDIUM
    targets: list[EventTarget]
    signals: EventSignals = Field(default_factory=EventSignals)
    provider_actions_already_active: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    timeline: list[EventTimelineEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_event(self) -> DdosEvent:
        if self.started_at is None and self.observed_at is None:
            raise ValueError("started_at or observed_at is required")
        if not self.targets:
            raise ValueError("targets is required")
        return self


class Organization(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    default_ttl_minutes: int | None = None
    maintenance_contact: str | None = None
    incident_commander_contact: str | None = None
    sector: str | None = None
    operating_model: str | None = None
    regions: list[str] = Field(default_factory=list)
    customer_segments: list[str] = Field(default_factory=list)
    critical_operating_periods: list[CriticalOperatingPeriod] = Field(default_factory=list)


class TrustedSourceGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str | None = None
    cidrs: list[str] = Field(default_factory=list)
    last_reviewed_at: date | None = None
    review_owner: str | None = None
    review_cadence_days: int | None = None
    exception_process: str | None = None
    emergency_override_process: str | None = None

    @field_validator("cidrs")
    @classmethod
    def validate_cidrs(cls, value: list[str]) -> list[str]:
        for cidr in value:
            validate_ip_or_cidr(cidr)
        return value


class ServiceEndpoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    ip: str
    protocol: str = "any"
    ports: list[int | str]
    exposure: EndpointExposure | None = None
    enforcement_points: list[EnforcementPoint] = Field(default_factory=list)
    shared_endpoint_group: str | None = None

    @field_validator("ip")
    @classmethod
    def valid_ip_or_cidr(cls, value: str) -> str:
        return validate_ip_or_cidr(value)

    @field_validator("protocol")
    @classmethod
    def normalize_protocol(cls, value: str) -> str:
        normalized = value.lower()
        if not normalized:
            raise ValueError("protocol must not be empty")
        return normalized

    @field_validator("ports")
    @classmethod
    def valid_ports(cls, value: list[int | str]) -> list[int | str]:
        if not value:
            raise ValueError("ports is required")
        for port in value:
            validate_port_spec(port)
        return value


class ServiceGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    display_name: str | None = None
    priority: Priority
    brownout_mode: BrownoutMode
    endpoints: list[ServiceEndpoint]
    trusted_source_groups: list[str] = Field(default_factory=list)
    max_ttl_minutes: int | None = None
    allowed_actions: list[ActionType]
    rollback_required: bool = True
    approval_required: bool = False
    business_process: str | None = None
    owner: str | None = None
    approver: str | None = None
    rollback_owner: str | None = None
    criticality_rationale: str | None = None
    rto_minutes: int | None = None
    rpo_minutes: int | None = None
    slo: str | None = None
    user_population: str | None = None
    revenue_impact: str | None = None
    public_safety_impact: str | None = None
    customer_tiers: list[str] = Field(default_factory=list)
    contractual_obligations: list[str] = Field(default_factory=list)
    regulated_workflows: list[str] = Field(default_factory=list)
    internal_only: bool = False
    depends_on: list[ServiceDependency] = Field(default_factory=list)
    maintenance_windows: list[MaintenanceWindow] = Field(default_factory=list)
    approval_metadata: ApprovalMetadata | None = None
    rollback_control: RollbackControl | None = None
    traffic_baseline: TrafficBaseline | None = None

    @field_validator("allowed_actions")
    @classmethod
    def non_empty_actions(cls, value: list[ActionType]) -> list[ActionType]:
        if not value:
            raise ValueError("allowed_actions is required")
        return value

    @field_validator("endpoints")
    @classmethod
    def non_empty_endpoints(cls, value: list[ServiceEndpoint]) -> list[ServiceEndpoint]:
        if not value:
            raise ValueError("endpoints is required")
        return value


class ServicePriorityFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    organization: Organization = Field(default_factory=Organization)
    trusted_sources: dict[str, TrustedSourceGroup] = Field(default_factory=dict)
    service_groups: list[ServiceGroup]

    @field_validator("service_groups")
    @classmethod
    def service_groups_required(cls, value: list[ServiceGroup]) -> list[ServiceGroup]:
        if not value:
            raise ValueError("service_groups is required")
        return value


class TtlPolicy(BaseModel):
    default_minutes: int = 30
    p0_max_minutes: int = 30
    p1_max_minutes: int = 30
    p2_max_minutes: int = 20
    p3_max_minutes: int = 15
    p4_max_minutes: int = 15
    null_route_max_minutes: int = 10


class RateLimitProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str | None = None
    abstract_rate: str | None = None
    exact_rate: str | dict[str, Any] | None = None
    applies_to: list[str] = Field(default_factory=list)

    @field_validator("applies_to")
    @classmethod
    def normalize_protocols(cls, value: list[str]) -> list[str]:
        return [item.lower() for item in value]


class PolicyPack(BaseModel):
    model_config = ConfigDict(extra="allow")

    pack_id: str
    description: str | None = None
    ttl: TtlPolicy = Field(default_factory=TtlPolicy)
    rate_limit_profiles: dict[str, RateLimitProfile] = Field(default_factory=dict)
    action_preferences: dict[Priority, list[ActionType]] = Field(default_factory=dict)
    risk_defaults: dict[ActionType, RiskLevel] = Field(default_factory=dict)


class SourceBlockingConfig(BaseModel):
    enabled_by_default: bool = False
    min_ipv4_prefix_length: int = 24
    min_ipv6_prefix_length: int = 64
    require_spoofing_likely_false: bool = True


class NullRouteConfig(BaseModel):
    enabled_by_default: bool = False
    p0_allowed: bool = False
    p1_allowed: bool = False
    require_allow_flag: bool = True


class CompilerConfig(BaseModel):
    default_ttl_minutes: int = 30
    max_ttl_minutes: int = 60
    p0_max_ttl_minutes: int = 30
    p1_max_ttl_minutes: int = 30
    p2_max_ttl_minutes: int = 20
    p3_max_ttl_minutes: int = 15
    p4_max_ttl_minutes: int = 15
    null_route_max_ttl_minutes: int = 10
    max_actions: int = 50
    allow_name_match: bool = False
    require_rollback: bool = True
    require_ttl: bool = True
    fail_on_p0_shed: bool = True
    fail_on_unmatched_event_targets: bool = False
    default_mode: Literal["REVIEW_ONLY"] = "REVIEW_ONLY"
    source_blocking: SourceBlockingConfig = Field(default_factory=SourceBlockingConfig)
    null_route: NullRouteConfig = Field(default_factory=NullRouteConfig)


class ActionTarget(BaseModel):
    ip: str
    protocol: str
    ports: list[int | str] | None = None


class BrownoutAction(BaseModel):
    action_id: str
    action_group_id: str | None = None
    action_group_role: str | None = None
    action_group_exclusive: bool = False
    action_type: ActionType
    service_id: str
    service_display_name: str | None = None
    service_priority: Priority
    brownout_mode: BrownoutMode
    business_process: str | None = None
    owner: str | None = None
    approver: str | None = None
    rollback_owner: str | None = None
    approval_metadata: dict[str, Any] = Field(default_factory=dict)
    rollback_control: dict[str, Any] = Field(default_factory=dict)
    target: ActionTarget
    selectors: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    ttl_minutes: int
    expires_at: datetime
    decision_required_by: datetime | None = None
    rollback_action_id: str
    approval_required: bool = False
    risk_level: RiskLevel
    confidence: Confidence
    reason_codes: list[str]
    reason_text: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    business_impact: list[str]
    suggested_operator_question: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    confidence_rationale: list[str] = Field(default_factory=list)
    collateral_scope: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)


class BrownoutPlan(BaseModel):
    plan_version: int = 1
    incident_id: str
    event_id: str
    generated_at: datetime
    expires_at: datetime
    mode: Literal["REVIEW_ONLY"] = "REVIEW_ONLY"
    action_count: int
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    blocker_details: list[dict[str, Any]] = Field(default_factory=list)
    action_groups: list[dict[str, Any]] = Field(default_factory=list)
    approval_bundle: dict[str, Any] = Field(default_factory=dict)
    source_evidence_review: dict[str, Any] = Field(default_factory=dict)
    executive_summary: dict[str, Any] = Field(default_factory=dict)
    handoff_bundle: dict[str, Any] = Field(default_factory=dict)
    decision_trace: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[BrownoutAction] = Field(default_factory=list)


class RollbackAction(BaseModel):
    rollback_action_id: str
    action_id: str
    service_id: str
    rollback_owner: str | None = None
    escalation_contact: str | None = None
    rollback_type: str = "REMOVE_TEMPORARY_POLICY"
    expected_policy_state_after_rollback: str = "pre-incident service policy restored"
    rollback_by: datetime
    verification_steps: list[str]
    evidence_required: list[str] = Field(default_factory=list)
    post_rollback_validation_status: str = "PENDING_OPERATOR_VERIFICATION"
    reason_codes: list[str]


class RollbackPlan(BaseModel):
    rollback_plan_version: int = 1
    incident_id: str
    event_id: str
    generated_at: datetime
    rollback_deadline: datetime
    rollback_required: bool = True
    rollback_actions: list[RollbackAction]


class ActionCsvRow(BaseModel):
    action_id: str
    action_type: str
    service_id: str
    service_display_name: str
    service_priority: str
    brownout_mode: str
    target_ip: str
    protocol: str
    ports: str
    ttl_minutes: int
    expires_at: str
    approval_required: bool
    risk_level: str
    reason_codes: str
    business_impact: str
    safety_notes: str
    rollback_action_id: str
    suggested_operator_question: str


class SummaryInput(BaseModel):
    event_targets: int
    service_groups: int
    matched_services: int
    unmatched_event_targets: int


class SummaryActions(BaseModel):
    total: int
    by_type: dict[str, int]
    by_priority: dict[str, int]
    approval_required: int


class Summary(BaseModel):
    incident_id: str
    event_id: str
    lint_status: str
    mode: Literal["REVIEW_ONLY"] = "REVIEW_ONLY"
    input: SummaryInput
    actions: SummaryActions
    risk: dict[str, int]
    warnings: list[str]
    blockers: list[str]
    confidence_distribution: dict[str, int] = Field(default_factory=dict)
    ttl_distribution: dict[str, int] = Field(default_factory=dict)
    rollback_deadlines: dict[str, str] = Field(default_factory=dict)
    services_by_business_process: dict[str, int] = Field(default_factory=dict)
    actions_by_owner: dict[str, int] = Field(default_factory=dict)
    actions_by_enforcement_point: dict[str, int] = Field(default_factory=dict)
    business_impact_totals: dict[str, int] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=list)
    recommended_operator_questions: list[str]


class ValidationResult(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    blocker_details: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers

    def extend(self, other: ValidationResult) -> None:
        self.warnings.extend(other.warnings)
        self.blockers.extend(other.blockers)
        self.blocker_details.extend(other.blocker_details)


class MatchResult(BaseModel):
    event_target: EventTarget
    service: ServiceGroup
    endpoint: ServiceEndpoint
    reason_codes: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.HIGH
    all_service_ids: list[str] = Field(default_factory=list)
