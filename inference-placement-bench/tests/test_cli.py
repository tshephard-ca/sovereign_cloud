from __future__ import annotations

import csv
import json

import pytest
from typer.testing import CliRunner

from inference_placement_bench.cli import app
from inference_placement_bench.config import DEFAULT_CONFIG
from inference_placement_bench.http_client import run_benchmark_plan, write_results_json
from inference_placement_bench.io_outputs import SAMPLE_COLUMNS, write_samples_csv
from inference_placement_bench.plan import build_plan
from inference_placement_bench.report import render_markdown_report
from inference_placement_bench.recommendation import build_recommendation

from conftest import (
    error_transport,
    make_constraints,
    make_endpoint,
    make_endpoint_profiles,
    make_workload,
    non_streaming_transport,
    streaming_transport,
)


def test_non_streaming_fake_endpoint_returns_parsed_text():
    plan = build_plan(
        make_workload(measured_requests=1, warmup_requests=0),
        make_endpoint_profiles(make_endpoint()),
        make_constraints(req_throughput=None, output_throughput=None),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    results = run_benchmark_plan(plan, DEFAULT_CONFIG, transport=non_streaming_transport(), now="2026-01-01T00:00:00Z")
    assert results.samples[0].status == "SUCCESS"
    assert results.samples[0].token_count_source == "EXACT_FROM_RESPONSE"


def test_streaming_fake_endpoint_returns_ttft_and_inter_token_metrics():
    plan = build_plan(
        make_workload(streaming_required=True, measured_requests=1, warmup_requests=0),
        make_endpoint_profiles(make_endpoint(streaming=True, response_mode="streaming")),
        make_constraints(req_throughput=None, output_throughput=None),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    results = run_benchmark_plan(plan, DEFAULT_CONFIG, transport=streaming_transport(), now="2026-01-01T00:00:00Z")
    sample = results.samples[0]
    assert sample.time_to_first_token_ms is not None
    assert sample.inter_token_latency_p50_ms is not None


def test_response_extractor_handles_simple_json_paths():
    from inference_placement_bench.response_extract import extract_json_path

    value, warnings = extract_json_path({"choices": [{"message": {"content": "ok"}}]}, "$.choices[0].message.content")
    assert value == "ok"
    assert warnings == []


def test_response_extractor_warns_missing_field():
    from inference_placement_bench.response_extract import extract_json_path

    value, warnings = extract_json_path({"choices": []}, "$.choices[0].message.content")
    assert value is None
    assert warnings == ["RESPONSE_EXTRACTOR_MISSING_FIELD"]


def test_samples_csv_has_exact_column_order(tmp_path):
    plan = build_plan(
        make_workload(measured_requests=1, warmup_requests=0),
        make_endpoint_profiles(make_endpoint()),
        make_constraints(req_throughput=None, output_throughput=None),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    results = run_benchmark_plan(plan, DEFAULT_CONFIG, transport=non_streaming_transport(), now="2026-01-01T00:00:00Z")
    output = tmp_path / "samples.csv"
    write_samples_csv(results.samples, str(output))
    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        assert next(reader) == SAMPLE_COLUMNS


def test_results_json_includes_aggregate_metrics(tmp_path):
    plan = build_plan(
        make_workload(measured_requests=1, warmup_requests=0),
        make_endpoint_profiles(make_endpoint()),
        make_constraints(req_throughput=None, output_throughput=None),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    results = run_benchmark_plan(plan, DEFAULT_CONFIG, transport=non_streaming_transport(), now="2026-01-01T00:00:00Z")
    output = tmp_path / "results.json"
    write_results_json(results, str(output))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "metrics" in payload["endpoints"][0]
    assert payload["endpoints"][0]["metrics"]["success_count"] == 1


def test_recommendation_md_includes_data_location_and_economics_caveats():
    plan = build_plan(
        make_workload(measured_requests=5, warmup_requests=0),
        make_endpoint_profiles(make_endpoint()),
        make_constraints(req_throughput=None, output_throughput=None),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    results = run_benchmark_plan(plan, DEFAULT_CONFIG, transport=non_streaming_transport(), now="2026-01-01T00:00:00Z")
    recommendation = build_recommendation(results, make_constraints(req_throughput=None, output_throughput=None), DEFAULT_CONFIG)
    report = render_markdown_report(recommendation)
    assert "Placement Decision" in report
    assert "Why This Endpoint Won" in report
    assert "Business Impact" in report
    assert "Data-location Constraint Result" in report
    assert "Unit economics" in report or "Unit Economics" in report
    assert "does not verify" in report


def test_strict_mode_fails_missing_credentials(monkeypatch):
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    from inference_placement_bench.models import EndpointAuth

    endpoint = make_endpoint(auth=EndpointAuth(type="bearer_env", token_env="MISSING_TOKEN"))
    plan = build_plan(make_workload(), make_endpoint_profiles(endpoint), make_constraints(), DEFAULT_CONFIG, strict=True)
    assert plan.endpoints[0].eligible is False
    assert "AUTH_ENV_MISSING" in plan.endpoints[0].eligibility_reason_codes


def test_strict_mode_fails_no_eligible_endpoints(project_root, tmp_path):
    runner = CliRunner()
    output = tmp_path / "plan.yml"
    endpoints = tmp_path / "endpoints.yml"
    endpoints.write_text(
        """
endpoints:
  - endpoint_id: endpoint_blocked
    base_url: https://endpoint-blocked.example.invalid
    auth:
      type: none
    declared_location:
      country: ZZ
      region: region-z
      data_zone: zone-z
      operator_control: local
    capabilities:
      workload_types:
        - embedding
      streaming: false
      max_context_window_tokens: 10
      max_output_tokens: 10
""",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "plan",
            "--workload",
            str(project_root / "examples/workloads/chat_support.yml"),
            "--endpoints",
            str(endpoints),
            "--constraints",
            str(project_root / "examples/constraints.yml"),
            "--output-plan",
            str(output),
            "--strict",
        ],
    )
    assert result.exit_code == 1


def test_dry_run_does_not_send_http_requests():
    plan = build_plan(
        make_workload(measured_requests=1, warmup_requests=0),
        make_endpoint_profiles(make_endpoint()),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    results = run_benchmark_plan(plan, DEFAULT_CONFIG, dry_run=True)
    assert results.samples == []
    assert results.endpoints[0].benchmark_status == "ELIGIBLE_NOT_RUN"


def test_no_network_mode_prevents_http_calls():
    plan = build_plan(
        make_workload(measured_requests=1, warmup_requests=0),
        make_endpoint_profiles(make_endpoint()),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    with pytest.raises(RuntimeError, match="NETWORK_DISABLED_BY_NO_NETWORK"):
        run_benchmark_plan(plan, DEFAULT_CONFIG, no_network=True)


def test_tests_use_fake_endpoints_only():
    assert non_streaming_transport() is not None
    assert streaming_transport() is not None
    assert error_transport() is not None


def test_no_test_requires_internet_access():
    plan = build_plan(
        make_workload(measured_requests=1, warmup_requests=0),
        make_endpoint_profiles(make_endpoint()),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    results = run_benchmark_plan(plan, DEFAULT_CONFIG, transport=non_streaming_transport(), no_network=True)
    assert results.samples[0].status == "SUCCESS"


def test_output_ordering_is_deterministic():
    plan_a = build_plan(
        make_workload(measured_requests=2, synthetic_prompt_count=2),
        make_endpoint_profiles(make_endpoint("endpoint_b"), make_endpoint("endpoint_a")),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    plan_b = build_plan(
        make_workload(measured_requests=2, synthetic_prompt_count=2),
        make_endpoint_profiles(make_endpoint("endpoint_b"), make_endpoint("endpoint_a")),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    assert [endpoint.endpoint_id for endpoint in plan_a.endpoints] == [endpoint.endpoint_id for endpoint in plan_b.endpoints]
