from __future__ import annotations

from inference_placement_bench.config import DEFAULT_CONFIG
from inference_placement_bench.models import AggregateMetrics
from inference_placement_bench.scoring import evaluate_benchmark_status

from conftest import make_constraints


def test_pass_endpoint_meets_latency_throughput_error_and_location_constraints():
    metrics = AggregateMetrics(
        measured_request_count=5,
        success_count=5,
        latency_p95_ms=900,
        requests_per_second=1,
        output_tokens_per_second=2,
        error_rate_pct=0,
        timeout_rate_pct=0,
        token_count_source_summary="EXACT_FROM_RESPONSE:5",
    )
    status, reasons, _ = evaluate_benchmark_status(metrics, make_constraints(), DEFAULT_CONFIG, True, ["ECONOMICS_PRESENT"])
    assert status == "PASS"
    assert "LATENCY_TARGET_MET" in reasons


def test_review_only_and_capacity_caveats_are_not_actionable_warnings():
    metrics = AggregateMetrics(
        measured_request_count=5,
        success_count=5,
        latency_p95_ms=900,
        requests_per_second=1,
        output_tokens_per_second=2,
        error_rate_pct=0,
        timeout_rate_pct=0,
        token_count_source_summary="EXACT_FROM_RESPONSE:5",
    )
    _status, reasons, warnings = evaluate_benchmark_status(metrics, make_constraints(), DEFAULT_CONFIG, True, ["ECONOMICS_PRESENT"])
    assert "REVIEW_ONLY_OUTPUT" in reasons
    assert "REVIEW_ONLY_OUTPUT" not in warnings
    assert "BENCHMARK_IS_NOT_CAPACITY_TEST" not in warnings


def test_review_endpoint_near_latency_miss_margin():
    metrics = AggregateMetrics(
        measured_request_count=5,
        success_count=5,
        latency_p95_ms=1050,
        requests_per_second=1,
        output_tokens_per_second=2,
        error_rate_pct=0,
        timeout_rate_pct=0,
        token_count_source_summary="EXACT_FROM_RESPONSE:5",
    )
    status, reasons, _ = evaluate_benchmark_status(metrics, make_constraints(latency_target=1000), DEFAULT_CONFIG, True, ["ECONOMICS_PRESENT"])
    assert status == "REVIEW"
    assert "LATENCY_TARGET_MISSED" in reasons


def test_fail_endpoint_misses_p95_latency_beyond_margin():
    metrics = AggregateMetrics(
        measured_request_count=5,
        success_count=5,
        latency_p95_ms=1300,
        requests_per_second=1,
        output_tokens_per_second=2,
        error_rate_pct=0,
        timeout_rate_pct=0,
        token_count_source_summary="EXACT_FROM_RESPONSE:5",
    )
    status, _, _ = evaluate_benchmark_status(metrics, make_constraints(latency_target=1000), DEFAULT_CONFIG, True, ["ECONOMICS_PRESENT"])
    assert status == "FAIL"


def test_fail_endpoint_exceeds_error_rate_target():
    metrics = AggregateMetrics(
        measured_request_count=5,
        success_count=4,
        error_count=1,
        latency_p95_ms=900,
        requests_per_second=1,
        output_tokens_per_second=2,
        error_rate_pct=20,
        timeout_rate_pct=0,
        token_count_source_summary="EXACT_FROM_RESPONSE:4",
    )
    status, reasons, _ = evaluate_benchmark_status(metrics, make_constraints(error_target=1), DEFAULT_CONFIG, True, ["ECONOMICS_PRESENT"])
    assert status == "FAIL"
    assert "ERROR_RATE_TARGET_MISSED" in reasons
