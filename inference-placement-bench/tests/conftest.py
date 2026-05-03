from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from inference_placement_bench.models import (
    AggregateMetrics,
    BenchmarkResults,
    BenchmarkSettings,
    Constraints,
    DataLocationConstraints,
    DeclaredLocation,
    EconomicsConstraints,
    EndpointAuth,
    EndpointCapabilities,
    EndpointProfile,
    EndpointProfiles,
    LatencyTargets,
    ModelProfile,
    NonStreamingExtractors,
    RecommendationSettings,
    ReliabilityTargets,
    RequestTemplate,
    ResponseExtractors,
    StreamingExtractors,
    ThroughputTargets,
    UnitEconomics,
    WorkloadProfile,
)


@pytest.fixture()
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def make_workload(
    *,
    workload_type: str = "chat_text",
    streaming_required: bool = False,
    measured_requests: int = 5,
    warmup_requests: int = 1,
    synthetic_prompt_count: int = 5,
) -> WorkloadProfile:
    return WorkloadProfile(
        workload_id="workload_one",
        workload_type=workload_type,
        model=ModelProfile(
            declared_model_name="generic-model",
            model_family="chat",
            min_context_window_tokens=1000,
            expected_input_tokens_p50=100,
            expected_input_tokens_p95=200,
            expected_output_tokens_p50=20,
            expected_output_tokens_p95=50,
            streaming_required=streaming_required,
        ),
        benchmark=BenchmarkSettings(
            synthetic_prompt_count=synthetic_prompt_count,
            warmup_requests=warmup_requests,
            measured_requests=measured_requests,
            concurrency=1,
            request_timeout_seconds=5,
        ),
        request=RequestTemplate(
            method="POST",
            path="/infer",
            headers={"Content-Type": "application/json"},
            body_template={
                "model": "{{model_name}}",
                "prompt": "{{prompt}}",
                "max_tokens": "{{max_output_tokens}}",
                "stream": "{{streaming}}",
            },
        ),
        response_extractors=ResponseExtractors(
            non_streaming=NonStreamingExtractors(
                text_json_path="$.choices[0].message.content",
                usage_input_tokens_json_path="$.usage.prompt_tokens",
                usage_output_tokens_json_path="$.usage.completion_tokens",
            ),
            streaming=StreamingExtractors(
                event_text_json_path="$.choices[0].delta.content",
                finish_reason_json_path="$.choices[0].finish_reason",
                usage_input_tokens_json_path="$.usage.prompt_tokens",
                usage_output_tokens_json_path="$.usage.completion_tokens",
            ),
        ),
    )


def make_endpoint(
    endpoint_id: str = "endpoint_a",
    *,
    streaming: bool = False,
    response_mode: str = "non_streaming",
    country: str = "CA",
    region: str = "region-a",
    data_zone: str = "ca-zone-1",
    operator_control: str = "local",
    workload_types: list[str] | None = None,
    max_context_window_tokens: int = 4096,
    max_output_tokens: int = 256,
    economics: bool = True,
    auth: EndpointAuth | None = None,
) -> EndpointProfile:
    return EndpointProfile(
        endpoint_id=endpoint_id,
        display_name=f"{endpoint_id} display",
        base_url=f"https://{endpoint_id}.example.invalid",
        model_name="generic-model",
        response_mode=response_mode,
        auth=auth or EndpointAuth(type="none"),
        declared_location=DeclaredLocation(
            country=country,
            region=region,
            data_zone=data_zone,
            operator_control=operator_control,
        ),
        capabilities=EndpointCapabilities(
            workload_types=workload_types or ["chat_text", "completion_text", "embedding"],
            streaming=streaming,
            max_context_window_tokens=max_context_window_tokens,
            max_output_tokens=max_output_tokens,
        ),
        unit_economics=UnitEconomics(
            currency="CAD",
            input_per_1m_tokens=1.0,
            output_per_1m_tokens=2.0,
            per_1k_requests=0.1,
        )
        if economics
        else None,
    )


def make_constraints(
    *,
    latency_target: float = 1000,
    req_throughput: float | None = 0.01,
    output_throughput: float | None = 0.01,
    error_target: float = 1.0,
    objective: str = "balanced",
) -> Constraints:
    return Constraints(
        constraint_id="constraint_one",
        data_location=DataLocationConstraints(
            allowed_countries=["CA"],
            allowed_regions=["region-a", "region-b"],
            allowed_data_zones=["ca-zone-1", "ca-zone-2"],
            allowed_operator_control=["local", "partner"],
            require_declared_location=True,
        ),
        latency_targets=LatencyTargets(
            end_to_end_p95_ms=latency_target,
            time_to_first_token_p95_ms=None,
            inter_token_latency_p95_ms=None,
        ),
        throughput_targets=ThroughputTargets(
            min_requests_per_second=req_throughput,
            min_output_tokens_per_second=output_throughput,
        ),
        reliability_targets=ReliabilityTargets(
            max_error_rate_pct=error_target,
            max_timeout_rate_pct=1.0,
        ),
        economics=EconomicsConstraints(currency="CAD"),
        recommendation=RecommendationSettings(objective=objective),
    )


def make_endpoint_profiles(*endpoints: EndpointProfile) -> EndpointProfiles:
    return EndpointProfiles(endpoints=list(endpoints))


def non_streaming_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "synthetic response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6},
            },
        )

    return httpx.MockTransport(handler)


def streaming_transport(done: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payloads = [
            {"choices": [{"delta": {"content": "one"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": " two"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 6}},
        ]
        body = "".join(f"data: {json.dumps(payload)}\n\n" for payload in payloads)
        if done:
            body += "data: [DONE]\n\n"
        return httpx.Response(200, content=body, headers={"Content-Type": "text/event-stream"})

    return httpx.MockTransport(handler)


def error_transport(status_code: int = 500) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="synthetic error")

    return httpx.MockTransport(handler)


def make_results_with_endpoint(
    *,
    endpoint_id: str,
    status: str,
    latency: float | None = 100,
    rps: float | None = 1.0,
    cost: float | str | None = 1.0,
    error_rate: float = 0.0,
    reason_codes: list[str] | None = None,
) -> BenchmarkResults:
    from inference_placement_bench.models import EndpointResult

    metrics = AggregateMetrics(
        measured_request_count=5,
        success_count=5 if status in {"PASS", "REVIEW"} else 0,
        latency_p95_ms=latency,
        requests_per_second=rps,
        output_tokens_per_second=10,
        error_rate_pct=error_rate,
        benchmark_status=status,
        reason_codes=reason_codes or ["DECLARED_LOCATION_ALLOWED"],
    )
    result = EndpointResult(
        endpoint_id=endpoint_id,
        eligibility_status="ELIGIBLE" if status != "INELIGIBLE" else "INELIGIBLE",
        benchmark_status=status,
        declared_location=DeclaredLocation(country="CA", region="region-a", data_zone="ca-zone-1", operator_control="local"),
        metrics=metrics,
        economics={"estimated_cost_per_1k_requests": cost, "currency": "CAD"},
        reason_codes=reason_codes or ["DECLARED_LOCATION_ALLOWED"],
    )
    return BenchmarkResults(
        run_id="run",
        workload_id="workload_one",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        mode="MEASURED_HTTP",
        config={},
        endpoints=[result],
    )
