"""Pydantic models for parsed inputs, observations, findings, and summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["CRITICAL", "WARNING", "REVIEW", "INFO"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
PreflightStatus = Literal["PASS", "REVIEW", "FAIL"]
DecisionStatus = Literal["missing", "present", "accepted_risk", "review", "optional"]
DecisionImpact = Literal[
    "blocks_recovery_test",
    "needs_owner_review",
    "accepted_for_this_preflight",
    "included_in_recovery_scope",
    "informational",
]
EvidenceStrength = Literal["strong", "partial", "weak"]


SUPPORTED_CATEGORIES = {
    "dns_resolver",
    "directory_service",
    "kerberos_service",
    "global_catalog",
    "vpn_endpoint",
    "license_server",
    "database_host",
    "file_share",
    "time_service",
    "other_prerequisite",
}


class BackupInventoryRow(BaseModel):
    source_row: int
    workload_name: str
    fqdn: str = ""
    short_name: str = ""
    ip_addresses: list[str] = Field(default_factory=list)
    protected: bool = True
    recovery_set: str = ""
    include_in_recovery_set: bool | None = None
    aliases: list[str] = Field(default_factory=list)
    role_tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ProtectedSystem(BaseModel):
    source_row: int
    workload_name: str
    fqdn: str = ""
    short_name: str = ""
    ip_addresses: list[str] = Field(default_factory=list)
    recovery_set: str = ""
    include_in_recovery_set: bool | None = None
    aliases: list[str] = Field(default_factory=list)
    role_tags: list[str] = Field(default_factory=list)


class RecoverySet(BaseModel):
    name: str = ""
    systems: list[ProtectedSystem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DnsQueryRow(BaseModel):
    source_row: int
    timestamp: datetime | None = None
    timestamp_raw: str = ""
    client_ip: str = ""
    client_name: str = ""
    qname: str
    qtype: str = "UNKNOWN"
    rcode: str = ""
    answer_names: list[str] = Field(default_factory=list)
    answer_ips: list[str] = Field(default_factory=list)
    resolver_name: str = ""
    resolver_ip: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class ResolverHint(BaseModel):
    name: str = ""
    ip_addresses: list[str] = Field(default_factory=list)
    recovery_required: bool = True
    source_row: int = 0


class KnownPrereqRule(BaseModel):
    id: str
    display_name: str = ""
    category: str
    names: list[str] = Field(default_factory=list)
    qname_regex: list[str] = Field(default_factory=list)
    required_in_recovery_set: bool = True
    source_row: int = 0


class OwnerMapEntry(BaseModel):
    owner_team: str
    categories: list[str] = Field(default_factory=list)
    contact: str = ""
    notes: str = ""


class AcceptedRisk(BaseModel):
    id: str
    category: str = ""
    name: str = ""
    reason: str = ""
    expires: str = ""
    source_row: int = 0


class RecoverySetMetadata(BaseModel):
    name: str
    purpose: str = ""
    site: str = ""
    notes: str = ""


class RecoverySetMatch(BaseModel):
    present: bool
    match_basis: str = ""
    matched_systems: list[str] = Field(default_factory=list)


class QueryEvidence(BaseModel):
    category: str
    prerequisite_name: str
    prerequisite_target: str = ""
    prerequisite_target_ip: str = ""
    confidence: Confidence = "LOW"
    evidence_source: str = "dns_query_log"
    reason_codes: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source_rows: list[str] = Field(default_factory=list)
    protected_system: str = ""
    protected_system_key: str = ""
    client_mapped: bool = False
    client_match_basis: str = ""
    qname: str = ""
    answer_names: list[str] = Field(default_factory=list)
    answer_ips: list[str] = Field(default_factory=list)
    role_level: bool = False
    known_prereq: bool = False
    required_in_recovery_set: bool = True
    internal: bool = False
    weak_heuristic: bool = False


class ObservedPrerequisite(BaseModel):
    category: str
    prerequisite_name: str
    prerequisite_target: str = ""
    prerequisite_target_ip: str = ""
    confidence: Confidence = "LOW"
    present_in_recovery_set: bool = False
    match_basis: str = ""
    observed_query_count: int = 0
    observed_by_protected_systems: int = 0
    protected_systems: list[str] = Field(default_factory=list)
    example_qnames: list[str] = Field(default_factory=list)
    example_answer_names: list[str] = Field(default_factory=list)
    example_answer_ips: list[str] = Field(default_factory=list)
    evidence_source: str = "dns_query_log"
    reason_codes: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source_rows: list[str] = Field(default_factory=list)
    role_level: bool = False
    known_prereq: bool = False
    required_in_recovery_set: bool = True
    weak_heuristic: bool = False
    internal: bool = False


class Finding(BaseModel):
    severity: Severity
    confidence: Confidence
    finding_code: str
    category: str
    prerequisite_name: str
    prerequisite_target: str = ""
    prerequisite_target_ip: str = ""
    recovery_set: str = ""
    present_in_recovery_set: bool = False
    match_basis: str = ""
    observed_query_count: int = 0
    observed_by_protected_systems: int = 0
    example_protected_systems: list[str] = Field(default_factory=list)
    example_qnames: list[str] = Field(default_factory=list)
    example_answer_names: list[str] = Field(default_factory=list)
    example_answer_ips: list[str] = Field(default_factory=list)
    evidence_source: str = ""
    reason_codes: list[str] = Field(default_factory=list)
    suggested_action: str = ""
    suggested_human_question: str = ""
    missing_data: list[str] = Field(default_factory=list)
    source_rows: list[str] = Field(default_factory=list)


class Summary(BaseModel):
    schema_version: str = "1.0"
    tool_version: str = "0.1.0"
    lint_status: Literal["PASS", "REVIEW", "FAIL"]
    recovery_set: str = ""
    input: dict[str, int] = Field(default_factory=dict)
    evidence_quality: dict[str, Any] = Field(default_factory=dict)
    findings: dict[str, int] = Field(default_factory=dict)
    categories: dict[str, int] = Field(default_factory=dict)
    top_missing_prerequisites: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    recommended_next_questions: list[str] = Field(default_factory=list)
    run_metadata: dict[str, Any] = Field(default_factory=dict)
    window_comparison: list[dict[str, Any]] = Field(default_factory=list)


class PreflightDecision(BaseModel):
    prerequisite_id: str
    display_name: str
    category: str
    service_family: str
    status: DecisionStatus
    impact: DecisionImpact
    severity: Severity
    confidence: Confidence
    evidence_strength: EvidenceStrength
    owner_team: str = ""
    owner_contact: str = ""
    target: str = ""
    target_ip: str = ""
    present_in_recovery_set: bool = False
    match_basis: str = ""
    observed_by: list[str] = Field(default_factory=list)
    observed_by_count: int = 0
    observed_query_count: int = 0
    example_qnames: list[str] = Field(default_factory=list)
    example_answer_names: list[str] = Field(default_factory=list)
    example_answer_ips: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    human_question: str = ""
    audit_reason_codes: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    source_rows: list[str] = Field(default_factory=list)


class ServiceFamilyAssessment(BaseModel):
    service_family: str
    display_name: str
    status: PreflightStatus
    impact_summary: str
    owner_teams: list[str] = Field(default_factory=list)
    missing_count: int = 0
    review_count: int = 0
    present_count: int = 0
    accepted_risk_count: int = 0
    decisions: list[str] = Field(default_factory=list)


class EvidenceImprovementAction(BaseModel):
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    action: str
    reason: str
    related_metric: str = ""


class OwnerWorkItem(BaseModel):
    owner_team: str
    owner_contact: str = ""
    service_family: str
    category: str
    prerequisite_id: str
    prerequisite: str
    status: DecisionStatus
    impact: DecisionImpact
    severity: Severity
    evidence_strength: EvidenceStrength
    observed_query_count: int = 0
    observed_by_count: int = 0
    recommended_action: str = ""
    human_question: str = ""
    reason_codes: list[str] = Field(default_factory=list)


class PreflightAssessment(BaseModel):
    schema_version: str = "1.0"
    tool_version: str = "0.1.0"
    assessment_type: Literal["recovery_preflight_assessment"] = "recovery_preflight_assessment"
    recovery_set: str = ""
    decision: PreflightStatus
    business_impact: str
    executive_summary: list[str] = Field(default_factory=list)
    input_counts: dict[str, int] = Field(default_factory=dict)
    finding_counts: dict[str, int] = Field(default_factory=dict)
    service_families: list[ServiceFamilyAssessment] = Field(default_factory=list)
    decisions: list[PreflightDecision] = Field(default_factory=list)
    owner_work_items: list[OwnerWorkItem] = Field(default_factory=list)
    evidence_quality: dict[str, Any] = Field(default_factory=dict)
    evidence_improvement_actions: list[EvidenceImprovementAction] = Field(default_factory=list)
    top_recovery_scope_gaps: list[str] = Field(default_factory=list)
    recommended_next_questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    run_metadata: dict[str, Any] = Field(default_factory=dict)
