from __future__ import annotations

from typing import Any

from .models import AggregateMetrics, Constraints, EndpointStatus


def evaluate_benchmark_status(
    metrics: AggregateMetrics,
    constraints: Constraints,
    config: dict[str, Any],
    eligibility_ok: bool,
    existing_reason_codes: list[str] | None = None,
    existing_warnings: list[str] | None = None,
) -> tuple[EndpointStatus, list[str], list[str]]:
    reasons = list(existing_reason_codes or [])
    warnings = list(existing_warnings or [])
    if not eligibility_ok:
        return "INELIGIBLE", _unique(reasons), _unique(warnings)

    status: EndpointStatus = "PASS"
    if metrics.measured_request_count == 0:
        reasons.append("BENCHMARK_NOT_RUN")
        return "ELIGIBLE_NOT_RUN", _unique(reasons), _unique(warnings)

    reasons.append("BENCHMARK_COMPLETED")

    review_min = int(config.get("minimum_successful_requests_review", 5))
    if metrics.success_count >= review_min:
        reasons.append("SAMPLE_SIZE_SUFFICIENT")
    else:
        reasons.append("SAMPLE_SIZE_SMALL")
        warnings.append("SMALL_SAMPLE_SIZE")
        status = _worse(status, "REVIEW")

    if metrics.success_count == 0 and metrics.timeout_count == metrics.measured_request_count:
        reasons.append("ALL_REQUESTS_TIMED_OUT")
        return "FAIL", _unique(reasons), _unique(warnings)
    if metrics.success_count == 0 and metrics.error_count == metrics.measured_request_count:
        reasons.append("ALL_REQUESTS_FAILED")
        return "FAIL", _unique(reasons), _unique(warnings)

    margin = float(config.get("latency_miss_review_margin_pct", 10))
    latency_status, code = _threshold_upper(metrics.latency_p95_ms, constraints.latency_targets.end_to_end_p95_ms, margin, "LATENCY_TARGET")
    reasons.append(code)
    status = _worse(status, latency_status)

    ttft_status, code = _threshold_upper(
        metrics.time_to_first_token_p95_ms,
        constraints.latency_targets.time_to_first_token_p95_ms,
        margin,
        "TTFT_TARGET",
    )
    reasons.append(code)
    status = _worse(status, ttft_status)

    inter_status, code = _threshold_upper(
        metrics.inter_token_latency_p95_ms,
        constraints.latency_targets.inter_token_latency_p95_ms,
        margin,
        "INTER_TOKEN_LATENCY_TARGET",
    )
    reasons.append(code)
    status = _worse(status, inter_status)

    throughput_margin = float(config.get("throughput_miss_review_margin_pct", 10))
    req_status, code = _threshold_lower(
        metrics.requests_per_second,
        constraints.throughput_targets.min_requests_per_second,
        throughput_margin,
        "THROUGHPUT_TARGET",
    )
    reasons.append(code)
    status = _worse(status, req_status)

    out_status, code = _threshold_lower(
        metrics.output_tokens_per_second,
        constraints.throughput_targets.min_output_tokens_per_second,
        throughput_margin,
        "THROUGHPUT_TARGET",
    )
    if code not in reasons:
        reasons.append(code)
    status = _worse(status, out_status)

    error_target = constraints.reliability_targets.max_error_rate_pct
    if error_target is not None:
        if metrics.error_rate_pct <= error_target:
            reasons.append("ERROR_RATE_TARGET_MET")
            near = float(config.get("error_rate_near_threshold_pct", 0.5))
            if metrics.error_rate_pct >= max(0.0, error_target - near) and metrics.error_rate_pct > 0:
                warnings.append("HIGH_ERROR_RATE_NEAR_THRESHOLD")
        else:
            reasons.append("ERROR_RATE_TARGET_MISSED")
            status = "FAIL"
    else:
        reasons.append("ERROR_RATE_TARGET_MET")

    timeout_target = constraints.reliability_targets.max_timeout_rate_pct
    if timeout_target is not None:
        if metrics.timeout_rate_pct <= timeout_target:
            reasons.append("TIMEOUT_RATE_TARGET_MET")
        else:
            reasons.append("TIMEOUT_RATE_TARGET_MISSED")
            status = "FAIL"
    else:
        reasons.append("TIMEOUT_RATE_TARGET_MET")

    if metrics.token_count_source_summary and "EXACT_FROM_RESPONSE" in metrics.token_count_source_summary:
        reasons.append("TOKEN_USAGE_RETURNED")
    elif metrics.token_count_source_summary:
        reasons.append("TOKEN_COUNTS_ESTIMATED")
        warnings.append("TOKEN_COUNTS_ESTIMATED")
        status = _worse(status, "REVIEW")

    if "ECONOMICS_UNKNOWN" in reasons:
        status = _worse(status, "REVIEW")
        warnings.append("UNIT_ECONOMICS_MISSING")

    reasons.append("REVIEW_ONLY_OUTPUT")
    return status, _unique(reasons), _unique(warnings)


def score_endpoint(metrics: AggregateMetrics, constraints: Constraints, economics_value: float | None) -> float:
    weights = constraints.recommendation.weights.normalized()
    latency_score = _score_upper(metrics.latency_p95_ms, constraints.latency_targets.end_to_end_p95_ms)
    throughput_score = _score_lower(metrics.requests_per_second, constraints.throughput_targets.min_requests_per_second)
    economics_score = 50.0 if economics_value is None else max(0.0, min(100.0, economics_value))
    data_score = 100.0
    score = (
        weights["latency"] * latency_score
        + weights["throughput"] * throughput_score
        + weights["economics"] * economics_score
        + weights["data_location"] * data_score
    )
    return round(score, 4)


def _threshold_upper(value: float | None, target: float | None, margin_pct: float, prefix: str) -> tuple[EndpointStatus, str]:
    if target is None:
        return "PASS", f"{prefix}_MET"
    if value is None:
        return "REVIEW", f"{prefix}_MISSED"
    if value <= target:
        return "PASS", f"{prefix}_MET"
    if value <= target * (1 + margin_pct / 100):
        return "REVIEW", f"{prefix}_MISSED"
    return "FAIL", f"{prefix}_MISSED"


def _threshold_lower(value: float | None, target: float | None, margin_pct: float, prefix: str) -> tuple[EndpointStatus, str]:
    if target is None:
        return "PASS", f"{prefix}_MET"
    if value is None:
        return "REVIEW", f"{prefix}_MISSED"
    if value >= target:
        return "PASS", f"{prefix}_MET"
    if value >= target * (1 - margin_pct / 100):
        return "REVIEW", f"{prefix}_MISSED"
    return "FAIL", f"{prefix}_MISSED"


def _score_upper(value: float | None, target: float | None) -> float:
    if value is None:
        return 50.0
    if target is None or target <= 0:
        return 100.0
    return max(0.0, min(100.0, 100.0 * target / value))


def _score_lower(value: float | None, target: float | None) -> float:
    if value is None:
        return 50.0
    if target is None or target <= 0:
        return 100.0
    return max(0.0, min(100.0, 100.0 * value / target))


def _worse(left: EndpointStatus, right: EndpointStatus) -> EndpointStatus:
    order = {"PASS": 0, "ELIGIBLE_NOT_RUN": 1, "REVIEW": 2, "INELIGIBLE": 3, "FAIL": 4}
    return left if order[left] >= order[right] else right


def _unique(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen and not value.endswith("_MET") or value not in seen:
            out.append(value)
            seen.add(value)
    return out
