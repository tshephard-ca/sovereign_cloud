from __future__ import annotations

import math
from collections import Counter

from .models import AggregateMetrics, BenchmarkSample


def percentile(values: list[float], pct: float) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    rank = math.ceil(pct / 100 * len(clean))
    rank = max(1, min(rank, len(clean)))
    return clean[rank - 1]


def aggregate_samples(
    samples: list[BenchmarkSample],
    measured_wall_seconds: float,
    include_failures_in_latency: bool = False,
) -> AggregateMetrics:
    measured = [sample for sample in samples if sample.measured]
    successes = [sample for sample in measured if sample.status == "SUCCESS"]
    errors = [sample for sample in measured if sample.status == "ERROR"]
    timeouts = [sample for sample in measured if sample.status == "TIMEOUT" or sample.timed_out]
    latency_source = measured if include_failures_in_latency else successes
    latencies = [sample.end_to_end_latency_ms for sample in latency_source if sample.end_to_end_latency_ms is not None]
    ttft = [sample.time_to_first_token_ms for sample in successes if sample.time_to_first_token_ms is not None]
    inter_p50 = [sample.inter_token_latency_p50_ms for sample in successes if sample.inter_token_latency_p50_ms is not None]
    inter_p95 = [sample.inter_token_latency_p95_ms for sample in successes if sample.inter_token_latency_p95_ms is not None]
    input_tokens = [sample.input_tokens for sample in successes if sample.input_tokens is not None]
    output_tokens = [sample.output_tokens for sample in successes if sample.output_tokens is not None]
    token_sources = [sample.token_count_source or "UNKNOWN" for sample in successes]
    measured_count = len(measured)
    error_rate = len(errors) / measured_count * 100 if measured_count else 0.0
    timeout_rate = len(timeouts) / measured_count * 100 if measured_count else 0.0
    out_tokens_total = sum(output_tokens) if output_tokens else None
    req_per_sec = len(successes) / measured_wall_seconds if measured_wall_seconds > 0 else None
    out_per_sec = out_tokens_total / measured_wall_seconds if out_tokens_total is not None and measured_wall_seconds > 0 else None
    return AggregateMetrics(
        measured_request_count=measured_count,
        success_count=len(successes),
        error_count=len(errors),
        timeout_count=len(timeouts),
        error_rate_pct=round(error_rate, 4),
        timeout_rate_pct=round(timeout_rate, 4),
        latency_p50_ms=_round(percentile(latencies, 50)),
        latency_p95_ms=_round(percentile(latencies, 95)),
        latency_p99_ms=_round(percentile(latencies, 99)),
        time_to_first_token_p50_ms=_round(percentile(ttft, 50)),
        time_to_first_token_p95_ms=_round(percentile(ttft, 95)),
        inter_token_latency_p50_ms=_round(percentile(inter_p50, 50)),
        inter_token_latency_p95_ms=_round(percentile(inter_p95, 95)),
        requests_per_second=_round(req_per_sec),
        output_tokens_per_second=_round(out_per_sec),
        input_tokens_total=sum(input_tokens) if input_tokens else None,
        output_tokens_total=out_tokens_total,
        token_count_source_summary=_summarize_token_sources(token_sources),
    )


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _summarize_token_sources(sources: list[str]) -> str | None:
    if not sources:
        return None
    counter = Counter(sources)
    return ",".join(f"{key}:{counter[key]}" for key in sorted(counter))
