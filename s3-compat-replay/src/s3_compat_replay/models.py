from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


EvidenceSource = str
Severity = str


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CloudTrailEvent(StrictBaseModel):
    eventVersion: str | None = None
    eventTime: str | None = None
    eventSource: str | None = None
    eventName: str | None = None
    region: str | None = None
    sourceIPAddress: str | None = None
    userAgent: str | None = None
    requestParameters: dict[str, Any] | None = None
    responseElements: dict[str, Any] | None = None
    additionalEventData: dict[str, Any] | None = None
    errorCode: str | None = None
    errorMessage: str | None = None
    readOnly: bool | str | None = None
    resources: list[dict[str, Any]] | None = None
    recipientAccountId: str | None = None
    requestID: str | None = None
    eventID: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class KeyShape(StrictBaseModel):
    slash_depth: int = 0
    extension: str | None = None
    has_date_path: bool = False
    has_uuid_like_segment: bool = False
    has_numeric_id_segment: bool = False
    prefix_template: str = "{key}"
    key_length_bucket: str = "unknown"
    original_key_hash: str | None = None


class NormalizedS3Event(StrictBaseModel):
    event_time: str | None = None
    event_source: str | None = None
    event_name: str | None = None
    region: str | None = None
    source_ip: str | None = None
    user_agent: str | None = None
    bucket: str | None = None
    key: str | None = None
    key_shape: KeyShape | None = None
    operation_family: str = "unknown"
    request_parameters: dict[str, Any] = Field(default_factory=dict)
    response_elements: dict[str, Any] = Field(default_factory=dict)
    additional_event_data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    read_only: bool | None = None
    resources: list[dict[str, Any]] = Field(default_factory=list)
    recipient_account_id: str | None = None
    request_id: str | None = None
    event_id: str | None = None
    observed_features: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_source: list[EvidenceSource] = Field(default_factory=lambda: ["CLOUDTRAIL"])
    source_shape_hash: str | None = None


class OperationFamilyProfile(StrictBaseModel):
    count: int = 0
    event_names: dict[str, int] = Field(default_factory=dict)
    observed_features: list[str] = Field(default_factory=list)
    sample_event_ids: list[str] = Field(default_factory=list)


class TimeRange(StrictBaseModel):
    first_event_time: str | None = None
    last_event_time: str | None = None


class EvidenceQuality(StrictBaseModel):
    has_request_parameters: bool = False
    has_response_elements: bool = False
    has_additional_event_data: bool = False
    has_errors: bool = False
    truncated_or_missing_fields: bool = False


class UsageProfile(StrictBaseModel):
    schema_version: int = 1
    source_bucket: str
    event_count: int = 0
    processed_event_count: int = 0
    ignored_event_count: int = 0
    time_range: TimeRange = Field(default_factory=TimeRange)
    operation_families: dict[str, OperationFamilyProfile] = Field(default_factory=dict)
    observed_features: list[str] = Field(default_factory=list)
    key_shapes: list[KeyShape] = Field(default_factory=list)
    user_agents: list[str] = Field(default_factory=list)
    request_shapes: list[dict[str, Any]] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_quality: EvidenceQuality = Field(default_factory=EvidenceQuality)
    request_hint_features: list[str] = Field(default_factory=list)
    bucket_config_features: list[str] = Field(default_factory=list)


class RequestHints(StrictBaseModel):
    presigned: dict[str, Any] = Field(default_factory=dict)
    cors: dict[str, Any] = Field(default_factory=dict)
    metadata_headers: list[str] = Field(default_factory=list)
    object_tags: dict[str, Any] = Field(default_factory=dict)
    content_types: list[str] = Field(default_factory=list)
    conditional_requests: dict[str, Any] = Field(default_factory=dict)
    range_gets: dict[str, Any] = Field(default_factory=dict)
    object_lock: dict[str, Any] = Field(default_factory=dict)
    expected_error_shapes: dict[str, Any] = Field(default_factory=dict)
    body_classes: list[str] = Field(default_factory=list)
    presigned_expiration_buckets: list[int] = Field(default_factory=list)
    object_size_distribution: dict[str, Any] = Field(default_factory=dict)
    requester_pays: dict[str, Any] = Field(default_factory=dict)
    pagination: dict[str, Any] = Field(default_factory=dict)
    consistency_expectations: dict[str, Any] = Field(default_factory=dict)


class BucketConfig(StrictBaseModel):
    versioning: dict[str, Any] = Field(default_factory=dict)
    object_lock: dict[str, Any] = Field(default_factory=dict)
    cors: dict[str, Any] = Field(default_factory=dict)
    lifecycle: dict[str, Any] = Field(default_factory=dict)
    ownership_controls: dict[str, Any] = Field(default_factory=dict)
    requester_pays: bool | None = None
    encryption: dict[str, Any] = Field(default_factory=dict)
    replication: dict[str, Any] = Field(default_factory=dict)
    event_notifications: dict[str, Any] = Field(default_factory=dict)
    policy_context: dict[str, Any] = Field(default_factory=dict)


class ProbeStep(StrictBaseModel):
    operation: str
    key_suffix: str | None = None
    body: str | bytes | None = None
    content_type: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    expect: dict[str, Any] = Field(default_factory=dict)


class Probe(StrictBaseModel):
    id: str
    family: str
    required: bool = True
    evidence_source: list[EvidenceSource] = Field(default_factory=list)
    synthetic_key_shape: KeyShape | None = None
    setup: list[ProbeStep] = Field(default_factory=list)
    steps: list[ProbeStep] = Field(default_factory=list)
    requires_allow_writes: bool = False
    requires_allow_deletes: bool = False
    requires_allow_acl_tests: bool = False
    requires_allow_multipart: bool = False
    requires_allow_object_lock_tests: bool = False
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProbePlan(StrictBaseModel):
    schema_version: int = 1
    plan_version: int = 1
    source_bucket: str
    generated_at: str
    scratch_prefix: str = "compat-replay/"
    safety: dict[str, Any] = Field(default_factory=dict)
    probes: list[Probe] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Mismatch(StrictBaseModel):
    severity: Severity = "INFO"
    probe_id: str
    operation_family: str
    operation: str
    evidence_source: str = "SYNTHETIC_PROBE"
    expected: str
    actual: str
    mismatch_code: str
    reason_text: str
    business_impact: str
    suggested_human_question: str


class ProbeStepResult(StrictBaseModel):
    operation: str
    status_code: int | None = None
    error_code: str | None = None
    critical_headers: dict[str, str] = Field(default_factory=dict)
    duration_ms: int | None = None
    mismatches: list[Mismatch] = Field(default_factory=list)


class ProbeResult(StrictBaseModel):
    probe_id: str
    family: str
    status: str = "PASS"
    severity: Severity = "INFO"
    steps: list[ProbeStepResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    mismatches: list[Mismatch] = Field(default_factory=list)


class CleanupManifest(StrictBaseModel):
    schema_version: int = 1
    run_id: str
    target_bucket_redacted: str
    scratch_prefix: str
    objects: list[str] = Field(default_factory=list)
    reason: str


class ProbeResults(StrictBaseModel):
    schema_version: int = 1
    result_source: str = "live_probe"
    run_id: str
    endpoint_url_redacted: str
    target_bucket_redacted: str
    scratch_prefix: str
    started_at: str
    finished_at: str
    probes_run: int = 0
    probes_skipped: int = 0
    probes_failed: int = 0
    cleanup: dict[str, Any] = Field(default_factory=dict)
    results: list[ProbeResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CompatibilitySummary(StrictBaseModel):
    schema_version: int = 1
    compatibility_status: str
    evidence_coverage_status: str = "REVIEW"
    target_semantic_status: str = "REVIEW"
    cutover_recommendation: str = "REVIEW"
    confidence: str
    source_profile: dict[str, Any]
    coverage: dict[str, int]
    mismatch_counts: dict[str, int]
    top_risks: list[dict[str, str]]
    recommended_next_questions: list[str]
    warnings: list[str] = Field(default_factory=list)


class RedactionChecks(StrictBaseModel):
    raw_bucket_names_found: int = 0
    raw_object_keys_found: int = 0
    account_ids_found: int = 0
    ip_addresses_found: int = 0
    arns_found: int = 0
    endpoint_hostnames_found: int = 0
    presigned_signatures_found: int = 0
    access_key_like_tokens_found: int = 0
    provider_names_found: int = 0


class RedactionFinding(StrictBaseModel):
    code: str
    path: str
    count: int
    sample: str | None = None


class RedactionReport(StrictBaseModel):
    schema_version: int = 1
    redaction_status: str = "PASS"
    checks: RedactionChecks = Field(default_factory=RedactionChecks)
    findings: list[RedactionFinding] = Field(default_factory=list)
    shareable: bool = True
    notes: list[str] = Field(default_factory=list)


class CaseBundleManifest(StrictBaseModel):
    schema_version: int = 1
    case_id: str
    created_at: str
    workload_type: str = "unspecified"
    event_count_bucket: str = "unknown"
    time_range_days: int | None = None
    observed_families: list[str] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    redaction_level: str = "shareable"
    source_provider: str = "redacted"
    target_provider: str = "redacted"
    artifacts: dict[str, str] = Field(default_factory=dict)
    business_outcome: dict[str, Any] = Field(default_factory=dict)


class QuestionnaireItem(StrictBaseModel):
    id: str
    severity: str = "REVIEW"
    category: str
    owner_role: str = "application owner"
    question: str
    reason: str
    answer_required: bool = True
    blocks_cutover_if_unanswered: bool = False
    evidence_source: list[str] = Field(default_factory=list)
    related_codes: list[str] = Field(default_factory=list)
    related_probe_ids: list[str] = Field(default_factory=list)


class Questionnaire(StrictBaseModel):
    schema_version: int = 1
    source_bucket_redacted: str | None = None
    generated_from: dict[str, str] = Field(default_factory=dict)
    questions: list[QuestionnaireItem] = Field(default_factory=list)


class FieldReview(StrictBaseModel):
    schema_version: int = 1
    reviewed_by_role: str | None = None
    blocker_confirmed: list[str] = Field(default_factory=list)
    false_positive: list[str] = Field(default_factory=list)
    missed_issue: list[dict[str, str]] = Field(default_factory=list)
    cutover_prevented_issue: bool | None = None
    confidence_after_review: str | None = None
    notes_redacted: bool = True


class PolicyPack(StrictBaseModel):
    schema_version: int = 1
    name: str
    description: str = ""
    workload_type: str = "unspecified"
    required_families: list[str] = Field(default_factory=list)
    severity_overrides: dict[str, str] = Field(default_factory=dict)
    required_hints: list[str] = Field(default_factory=list)
    evidence_quality_minimum: str = "MEDIUM"
    human_questions: list[str] = Field(default_factory=list)


class PolicyEvaluation(StrictBaseModel):
    schema_version: int = 1
    policy_name: str
    status: str
    evidence_policy_status: str = "REVIEW"
    target_policy_status: str = "NOT_RUN"
    missing_required_families: list[str] = Field(default_factory=list)
    missing_required_hints: list[str] = Field(default_factory=list)
    severity_overrides_applied: dict[str, str] = Field(default_factory=dict)
    blocker_mismatch_codes: list[str] = Field(default_factory=list)
    review_mismatch_codes: list[str] = Field(default_factory=list)
    recommended_questions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CorpusSummary(StrictBaseModel):
    schema_version: int = 1
    case_count: int = 0
    workload_types: dict[str, int] = Field(default_factory=dict)
    observed_families: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    mismatch_code_counts: dict[str, int] = Field(default_factory=dict)
    blocker_code_counts: dict[str, int] = Field(default_factory=dict)
    review_code_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ValidationResult(StrictBaseModel):
    schema_version: int = 1
    status: str
    artifact_type: str
    path: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MatrixTargetSummary(StrictBaseModel):
    target_id: str
    compatibility_status: str
    probes_run: int
    probes_failed: int
    probes_skipped: int
    blocker_count: int
    review_count: int
    info_count: int
    top_codes: list[str] = Field(default_factory=list)


class CompatibilityMatrix(StrictBaseModel):
    schema_version: int = 1
    generated_at: str
    target_count: int
    targets: list[MatrixTargetSummary] = Field(default_factory=list)
    recommended_questions: list[str] = Field(default_factory=list)


class RealWorldGeneratedFixture(StrictBaseModel):
    schema_version: int = 1
    source_bucket: str
    generated_at: str
    event_count: int
    files: dict[str, str] = Field(default_factory=dict)
    workload_types: list[str] = Field(default_factory=list)
    operation_families: list[str] = Field(default_factory=list)
    intended_business_risks: list[str] = Field(default_factory=list)


class GapFinding(StrictBaseModel):
    area: str
    severity: str
    code: str
    description: str
    business_impact: str
    suggested_action: str


class RealWorldDataAssessment(StrictBaseModel):
    schema_version: int = 1
    status: str
    input_coverage: dict[str, Any] = Field(default_factory=dict)
    output_coverage: dict[str, Any] = Field(default_factory=dict)
    business_impact_findings: list[dict[str, str]] = Field(default_factory=list)
    input_gaps: list[GapFinding] = Field(default_factory=list)
    output_gaps: list[GapFinding] = Field(default_factory=list)
    realism_notes: list[str] = Field(default_factory=list)


class CapabilityFinding(StrictBaseModel):
    capability: str
    business_flow: str
    owner_role: str
    why_it_matters: str
    observed_evidence: list[str] = Field(default_factory=list)
    required_by_workflow: bool = False
    probe_ids: list[str] = Field(default_factory=list)
    probe_status: str = "NOT_RUN"
    severity: str = "INFO"
    mismatch_codes: list[str] = Field(default_factory=list)
    next_action: str


class RemediationItem(StrictBaseModel):
    severity: str
    capability: str
    business_flow: str
    owner_role: str
    probe_id: str
    mismatch_code: str
    business_impact: str
    next_action: str
    question: str


class EvidenceLedgerItem(StrictBaseModel):
    evidence_type: str
    item: str
    source: str
    notes: str = ""


class SafetyGateSummary(StrictBaseModel):
    scratch_prefix: str
    synthetic_objects_only: bool = True
    writes_require_flag: bool = True
    deletes_require_flag: bool = True
    acl_tests_require_flag: bool = True
    multipart_tests_require_flag: bool = True
    object_lock_tests_require_flag: bool = True
    source_bucket_accessed: bool = False
    unsafe_probe_count: int = 0
    skipped_probe_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class CutoverDecisionBrief(StrictBaseModel):
    schema_version: int = 1
    cutover_recommendation: str
    evidence_coverage_status: str
    target_semantic_status: str
    confidence: str
    business_throughline: str
    source_bucket_redacted: str
    result_source: str = "not-run"
    first_read: dict[str, Any] = Field(default_factory=dict)
    affected_business_flows: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[RemediationItem] = Field(default_factory=list)
    review_items: list[RemediationItem] = Field(default_factory=list)
    owner_questions: list[QuestionnaireItem] = Field(default_factory=list)
    capability_ledger: list[CapabilityFinding] = Field(default_factory=list)
    evidence_ledger: list[EvidenceLedgerItem] = Field(default_factory=list)
    safety_gates: SafetyGateSummary
    untested_assumptions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
