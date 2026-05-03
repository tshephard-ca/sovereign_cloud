from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


WorkloadType = Literal[
    "chat_text",
    "completion_text",
    "embedding",
    "rerank",
    "classification",
    "summarization",
]
ResponseMode = Literal["streaming", "non_streaming"]
AuthType = Literal["none", "bearer_env", "header_env"]
Objective = Literal[
    "lowest_latency",
    "highest_throughput",
    "lowest_unit_cost",
    "balanced",
    "eligible_only",
]
EndpointStatus = Literal["ELIGIBLE_NOT_RUN", "INELIGIBLE", "PASS", "REVIEW", "FAIL"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelProfile(StrictModel):
    declared_model_name: str | None = None
    model_family: str | None = None
    min_context_window_tokens: int | None = None
    expected_input_tokens_p50: int | None = None
    expected_input_tokens_p95: int | None = None
    expected_output_tokens_p50: int | None = None
    expected_output_tokens_p95: int | None = None
    streaming_required: bool = False

    @field_validator(
        "min_context_window_tokens",
        "expected_input_tokens_p50",
        "expected_input_tokens_p95",
        "expected_output_tokens_p50",
        "expected_output_tokens_p95",
    )
    @classmethod
    def non_negative_int(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("must be non-negative")
        return value


class BenchmarkSettings(StrictModel):
    prompt_file: str | None = None
    synthetic_prompt_count: int | None = None
    warmup_requests: int = 0
    measured_requests: int
    concurrency: int = 1
    request_timeout_seconds: float = 60
    random_seed: int = 12345

    @field_validator("measured_requests")
    @classmethod
    def measured_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("benchmark.measured_requests must be > 0")
        return value

    @field_validator("warmup_requests")
    @classmethod
    def warmup_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("benchmark.warmup_requests must be >= 0")
        return value

    @field_validator("concurrency")
    @classmethod
    def concurrency_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("benchmark.concurrency must be >= 1")
        return value

    @field_validator("request_timeout_seconds")
    @classmethod
    def timeout_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("benchmark.request_timeout_seconds must be > 0")
        return value

    @field_validator("prompt_file")
    @classmethod
    def prompt_file_jsonl(cls, value: str | None) -> str | None:
        if value and not value.endswith(".jsonl"):
            raise ValueError("benchmark.prompt_file must be JSONL")
        return value

    @model_validator(mode="after")
    def prompt_source_required(self) -> "BenchmarkSettings":
        if not self.prompt_file and not self.synthetic_prompt_count:
            raise ValueError("prompt_file or synthetic_prompt_count is required")
        if self.synthetic_prompt_count is not None and self.synthetic_prompt_count <= 0:
            raise ValueError("synthetic_prompt_count must be > 0")
        return self


class RequestTemplate(StrictModel):
    method: Literal["GET", "POST"] = "POST"
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: dict[str, Any] = Field(default_factory=dict)


class NonStreamingExtractors(StrictModel):
    text_json_path: str | None = None
    usage_input_tokens_json_path: str | None = None
    usage_output_tokens_json_path: str | None = None


class StreamingExtractors(StrictModel):
    event_text_json_path: str | None = None
    finish_reason_json_path: str | None = None
    usage_input_tokens_json_path: str | None = None
    usage_output_tokens_json_path: str | None = None


class ResponseExtractors(StrictModel):
    non_streaming: NonStreamingExtractors | None = None
    streaming: StreamingExtractors | None = None


class WorkloadProfile(StrictModel):
    workload_id: str
    display_name: str | None = None
    workload_type: WorkloadType
    model: ModelProfile
    benchmark: BenchmarkSettings
    request: RequestTemplate
    response_extractors: ResponseExtractors = Field(default_factory=ResponseExtractors)


class EndpointAuth(StrictModel):
    type: AuthType = "none"
    token_env: str | None = None
    header_name: str | None = None

    @model_validator(mode="after")
    def auth_fields_valid(self) -> "EndpointAuth":
        if self.type in {"bearer_env", "header_env"} and not self.token_env:
            raise ValueError("token_env is required for environment-sourced auth")
        if self.type == "header_env" and not self.header_name:
            raise ValueError("header_name is required for header_env auth")
        if self.type == "bearer_env" and self.header_name:
            raise ValueError("header_name is not used for bearer_env auth")
        return self


class DeclaredLocation(StrictModel):
    country: str | None = None
    region: str | None = None
    data_zone: str | None = None
    operator_control: str | None = None


class EndpointCapabilities(StrictModel):
    workload_types: list[WorkloadType] = Field(default_factory=list)
    streaming: bool = False
    max_context_window_tokens: int | None = None
    max_output_tokens: int | None = None


class UnitEconomics(StrictModel):
    currency: str | None = None
    input_per_1m_tokens: float | None = None
    output_per_1m_tokens: float | None = None
    per_1k_requests: float | None = None
    per_request: float | None = None
    monthly_commit: float | None = None
    minimum_monthly_commit: float | None = None
    notes: str | None = None

    @field_validator(
        "input_per_1m_tokens",
        "output_per_1m_tokens",
        "per_1k_requests",
        "per_request",
        "monthly_commit",
        "minimum_monthly_commit",
    )
    @classmethod
    def non_negative_money(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("economics values must be non-negative")
        return value


class RequestOverrides(StrictModel):
    path: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class EndpointSimulator(StrictModel):
    enabled: bool = False
    latency_ms: float = 25
    time_to_first_token_ms: float = 10
    inter_token_latency_ms: float = 5
    input_tokens: int = 100
    output_tokens: int = 40
    error_rate_pct: float = 0.0
    timeout_rate_pct: float = 0.0
    response_text: str = "Synthetic response for review-only benchmark."

    @field_validator(
        "latency_ms",
        "time_to_first_token_ms",
        "inter_token_latency_ms",
        "error_rate_pct",
        "timeout_rate_pct",
    )
    @classmethod
    def non_negative_float(cls, value: float) -> float:
        if value < 0:
            raise ValueError("simulator values must be non-negative")
        return value

    @field_validator("input_tokens", "output_tokens")
    @classmethod
    def non_negative_token_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("simulator token counts must be non-negative")
        return value


class EndpointProfile(StrictModel):
    endpoint_id: str
    display_name: str | None = None
    base_url: str
    model_name: str | None = None
    protocol: Literal["http_json"] = "http_json"
    response_mode: ResponseMode = "non_streaming"
    auth: EndpointAuth = Field(default_factory=EndpointAuth)
    declared_location: DeclaredLocation | None = None
    capabilities: EndpointCapabilities = Field(default_factory=EndpointCapabilities)
    unit_economics: UnitEconomics | None = None
    request_overrides: RequestOverrides | None = None
    simulator: EndpointSimulator | None = None


class EndpointProfiles(StrictModel):
    endpoints: list[EndpointProfile]

    @model_validator(mode="after")
    def endpoint_ids_unique(self) -> "EndpointProfiles":
        ids = [endpoint.endpoint_id for endpoint in self.endpoints]
        if len(ids) != len(set(ids)):
            raise ValueError("endpoint_id values must be unique")
        return self


class DataLocationConstraints(StrictModel):
    allowed_countries: list[str] | None = None
    allowed_regions: list[str] | None = None
    allowed_data_zones: list[str] | None = None
    allowed_operator_control: list[str] | None = None
    require_declared_location: bool = False


class LatencyTargets(StrictModel):
    end_to_end_p95_ms: float | None = None
    time_to_first_token_p95_ms: float | None = None
    inter_token_latency_p95_ms: float | None = None


class ThroughputTargets(StrictModel):
    min_requests_per_second: float | None = None
    min_output_tokens_per_second: float | None = None


class ReliabilityTargets(StrictModel):
    max_error_rate_pct: float | None = None
    max_timeout_rate_pct: float | None = None


class EconomicsConstraints(StrictModel):
    currency: str | None = None
    prefer_lower_cost_when_within_latency_margin_pct: float | None = None
    max_estimated_cost_per_1k_requests: float | None = None
    max_estimated_cost_per_1m_output_tokens: float | None = None
    require_token_usage: bool = False


class RecommendationWeights(StrictModel):
    latency: float = 40
    throughput: float = 20
    economics: float = 20
    data_location: float = 20

    def normalized(self) -> dict[str, float]:
        weights = self.model_dump()
        total = sum(max(v, 0) for v in weights.values())
        if total <= 0:
            return {key: 0.25 for key in weights}
        return {key: max(value, 0) / total for key, value in weights.items()}


class RecommendationSettings(StrictModel):
    objective: Objective = "balanced"
    weights: RecommendationWeights = Field(default_factory=RecommendationWeights)


class Constraints(StrictModel):
    constraint_id: str
    data_location: DataLocationConstraints = Field(default_factory=DataLocationConstraints)
    latency_targets: LatencyTargets = Field(default_factory=LatencyTargets)
    throughput_targets: ThroughputTargets = Field(default_factory=ThroughputTargets)
    reliability_targets: ReliabilityTargets = Field(default_factory=ReliabilityTargets)
    economics: EconomicsConstraints = Field(default_factory=EconomicsConstraints)
    recommendation: RecommendationSettings = Field(default_factory=RecommendationSettings)


class PromptRecord(StrictModel):
    id: str
    prompt: str
    input_tokens_estimate: int | None = None
    expected_output_tokens_estimate: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class BenchmarkStep(StrictModel):
    response_mode: ResponseMode
    request_count: int
    warmup_count: int
    prompt_ids: list[str]


class PlannedEndpoint(StrictModel):
    endpoint_id: str
    display_name: str | None = None
    base_url_redacted: str | None = None
    eligible: bool
    eligibility_reason_codes: list[str]
    benchmark: BenchmarkStep | None = None
    declared_location: DeclaredLocation | None = None


class BenchmarkPlan(StrictModel):
    plan_version: int = 1
    workload_id: str
    generated_at: str
    measured_requests: int
    warmup_requests: int
    concurrency: int
    request_timeout_seconds: float
    workload: WorkloadProfile
    constraints: Constraints
    endpoints: list[PlannedEndpoint]
    endpoint_profiles: list[EndpointProfile]
    prompts: list[PromptRecord]
    warnings: list[str] = Field(default_factory=list)


class BenchmarkSample(StrictModel):
    endpoint_id: str
    prompt_id: str
    measured: bool
    status: Literal["SUCCESS", "ERROR", "TIMEOUT"]
    http_status: int | None = None
    started_at: str
    end_to_end_latency_ms: float | None = None
    time_to_first_token_ms: float | None = None
    inter_token_latency_p50_ms: float | None = None
    inter_token_latency_p95_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_count_source: str | None = None
    output_tokens_per_second: float | None = None
    request_bytes: int | None = None
    response_bytes: int | None = None
    timed_out: bool = False
    retry_count: int = 0
    response_mode: ResponseMode
    source_row: int | None = None
    error_code: str | None = None
    error_text_redacted: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AggregateMetrics(StrictModel):
    measured_request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    error_rate_pct: float = 0.0
    timeout_rate_pct: float = 0.0
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    time_to_first_token_p50_ms: float | None = None
    time_to_first_token_p95_ms: float | None = None
    inter_token_latency_p50_ms: float | None = None
    inter_token_latency_p95_ms: float | None = None
    requests_per_second: float | None = None
    output_tokens_per_second: float | None = None
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    token_count_source_summary: str | None = None
    estimated_cost_per_1k_requests: float | str | None = None
    estimated_cost_per_1m_input_tokens: float | str | None = None
    estimated_cost_per_1m_output_tokens: float | str | None = None
    estimated_cost_for_benchmark_run: float | str | None = None
    eligibility_status: str | None = None
    benchmark_status: EndpointStatus | None = None
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EndpointResult(StrictModel):
    endpoint_id: str
    eligibility_status: Literal["ELIGIBLE", "INELIGIBLE"]
    benchmark_status: EndpointStatus
    declared_location: DeclaredLocation | None = None
    metrics: AggregateMetrics
    economics: dict[str, Any] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BenchmarkResults(StrictModel):
    run_id: str
    workload_id: str
    started_at: str
    finished_at: str
    mode: Literal["MEASURED_HTTP", "DRY_RUN"]
    config: dict[str, Any]
    endpoints: list[EndpointResult]
    samples: list[BenchmarkSample] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DecisionTableRow(StrictModel):
    endpoint_id: str
    status: EndpointStatus
    score: float
    latency_p95_ms: float | None = None
    time_to_first_token_p95_ms: float | None = None
    inter_token_latency_p95_ms: float | None = None
    requests_per_second: float | None = None
    output_tokens_per_second: float | None = None
    error_rate_pct: float | None = None
    timeout_rate_pct: float | None = None
    estimated_cost_per_1k_requests: float | str | None = None
    latency_headroom_ms: float | None = None
    ttft_headroom_ms: float | None = None
    cost_delta_vs_recommended_pct: float | None = None
    latency_delta_vs_fastest_pct: float | None = None
    data_location_status: Literal["PASS", "FAIL", "UNKNOWN"] = "UNKNOWN"
    primary_strength: str | None = None
    primary_risk: str | None = None
    why_not_selected: str | None = None
    summary: str


class RecommendationOutput(StrictModel):
    workload_id: str
    constraint_id: str
    recommendation_status: Literal[
        "RECOMMENDED",
        "NO_CLEAR_WINNER_REVIEW_REQUIRED",
        "NO_ENDPOINT_MEETS_CONSTRAINTS",
        "INSUFFICIENT_DATA",
    ]
    recommended_endpoint_id: str | None = None
    objective: Objective
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    reason_codes: list[str]
    placement_summary: dict[str, Any] = Field(default_factory=dict)
    business_impact: dict[str, Any] = Field(default_factory=dict)
    decision_table: list[DecisionTableRow]
    business_summary: dict[str, str]
    warnings: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    input_quality: dict[str, Any] = Field(default_factory=dict)
    sensitivity_analysis: list[dict[str, Any]] = Field(default_factory=list)
