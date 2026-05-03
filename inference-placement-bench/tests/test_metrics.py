from __future__ import annotations

from inference_placement_bench.metrics import aggregate_samples, percentile
from inference_placement_bench.models import BenchmarkSample


def sample(status="SUCCESS", measured=True, timeout=False, latency=100):
    return BenchmarkSample(
        endpoint_id="endpoint_a",
        prompt_id="p1",
        measured=measured,
        status=status,
        started_at="2026-01-01T00:00:00Z",
        end_to_end_latency_ms=latency,
        input_tokens=10 if status == "SUCCESS" else None,
        output_tokens=5 if status == "SUCCESS" else None,
        token_count_source="EXACT_FROM_RESPONSE" if status == "SUCCESS" else None,
        response_mode="non_streaming",
        timed_out=timeout,
    )


def test_percentile_calculation_is_deterministic():
    assert percentile([5, 1, 3, 2, 4], 95) == 5
    assert percentile([5, 1, 3, 2, 4], 50) == 3


def test_warmup_samples_excluded_from_aggregate_metrics():
    metrics = aggregate_samples([sample(measured=False), sample(measured=True)], measured_wall_seconds=1)
    assert metrics.measured_request_count == 1
    assert metrics.success_count == 1


def test_error_rate_calculated_correctly():
    metrics = aggregate_samples([sample(), sample(status="ERROR")], measured_wall_seconds=1)
    assert metrics.error_rate_pct == 50.0


def test_timeout_rate_calculated_correctly():
    metrics = aggregate_samples([sample(), sample(status="TIMEOUT", timeout=True)], measured_wall_seconds=1)
    assert metrics.timeout_rate_pct == 50.0
