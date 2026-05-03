from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BenchmarkResults, Constraints, DecisionTableRow, EndpointResult, RecommendationOutput
from .scoring import score_endpoint


CAVEATS = [
    "A micro-benchmark is not a production load test.",
    "Synthetic prompts may not match production prompt length, content, or cache behavior.",
    "p95 latency from a small run is only a directional signal.",
    "Endpoint capacity, queueing, throttling, and maintenance windows are not proven.",
    "Data-location metadata is declared by the user; this tool does not verify it.",
    "Unit economics are calculated from user-supplied rate cards; the tool does not fetch prices.",
    "Token counts may be estimates unless the endpoint returns usage.",
    "The fastest endpoint may fail a location or policy constraint.",
    "The cheapest endpoint may miss latency or reliability targets.",
    "Model answer quality is not evaluated.",
]


def build_recommendation(results: BenchmarkResults, constraints: Constraints, config: dict[str, Any] | None = None) -> RecommendationOutput:
    config = config or {}
    pass_results = [endpoint for endpoint in results.endpoints if endpoint.benchmark_status == "PASS"]
    review_results = [endpoint for endpoint in results.endpoints if endpoint.benchmark_status == "REVIEW"]
    not_run_results = [endpoint for endpoint in results.endpoints if endpoint.benchmark_status == "ELIGIBLE_NOT_RUN"]
    objective = constraints.recommendation.objective
    warnings = _unique([warning for endpoint in results.endpoints for warning in endpoint.warnings] + results.warnings)
    reason_codes: list[str] = []
    recommended: EndpointResult | None = None

    if not results.endpoints:
        status = "INSUFFICIENT_DATA"
        reason_codes.append("NO_PASSING_ENDPOINT")
    elif pass_results:
        recommended = _choose_pass_endpoint(pass_results, objective, constraints)
        status = "RECOMMENDED"
        reason_codes.extend(_recommend_reason_codes(pass_results, recommended, objective))
    elif review_results:
        status = "NO_CLEAR_WINNER_REVIEW_REQUIRED"
        reason_codes.extend(["NO_CLEAR_WINNER", "HUMAN_REVIEW_REQUIRED"])
    elif not_run_results:
        status = "INSUFFICIENT_DATA"
        reason_codes.extend(["NO_PASSING_ENDPOINT", "HUMAN_REVIEW_REQUIRED"])
    else:
        status = "NO_ENDPOINT_MEETS_CONSTRAINTS"
        reason_codes.append("NO_PASSING_ENDPOINT")

    rows = _decision_rows(results, constraints, recommended.endpoint_id if recommended else None, objective)
    confidence = _confidence(results, warnings, config)
    summary_text = _summary_text(status, recommended, constraints)
    placement_summary = _placement_summary(status, recommended, rows, objective, constraints)
    business_impact = _business_impact(results, recommended, rows, constraints)
    return RecommendationOutput(
        workload_id=results.workload_id,
        constraint_id=constraints.constraint_id,
        recommendation_status=status,
        recommended_endpoint_id=recommended.endpoint_id if recommended else None,
        objective=objective,
        confidence=confidence,
        reason_codes=_unique(reason_codes),
        placement_summary=placement_summary,
        business_impact=business_impact,
        decision_table=rows,
        business_summary={
            "text": summary_text,
            "recommended_next_step": "Run a longer benchmark with production-like prompts and confirm endpoint capacity, support terms, and data-handling commitments before production placement.",
        },
        warnings=warnings,
        caveats=CAVEATS,
        input_quality=_input_quality(results),
        sensitivity_analysis=_sensitivity_analysis(pass_results, recommended),
    )


def write_recommendation_json(recommendation: RecommendationOutput, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(recommendation.model_dump(mode="json"), indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _decision_rows(
    results: BenchmarkResults,
    constraints: Constraints,
    recommended_endpoint_id: str | None = None,
    objective: str = "balanced",
) -> list[DecisionTableRow]:
    economics_values = []
    for endpoint in results.endpoints:
        value = _known_float(endpoint.economics.get("estimated_cost_per_1k_requests"))
        if value is not None:
            economics_values.append(value)
    cheapest = min(economics_values) if economics_values else None
    fastest_latency = min(
        [
            endpoint.metrics.latency_p95_ms
            for endpoint in results.endpoints
            if endpoint.benchmark_status == "PASS" and endpoint.metrics.latency_p95_ms is not None
        ],
        default=None,
    )
    recommended_cost = None
    if recommended_endpoint_id:
        for endpoint in results.endpoints:
            if endpoint.endpoint_id == recommended_endpoint_id:
                recommended_cost = _known_float(endpoint.economics.get("estimated_cost_per_1k_requests"))
                break
    rows: list[DecisionTableRow] = []
    for endpoint in results.endpoints:
        cost = _known_float(endpoint.economics.get("estimated_cost_per_1k_requests"))
        econ_score = None
        if cost is not None and cheapest is not None and cost > 0:
            econ_score = max(0.0, min(100.0, 100.0 * cheapest / cost))
        score = 0.0 if endpoint.benchmark_status in {"FAIL", "INELIGIBLE"} else score_endpoint(endpoint.metrics, constraints, econ_score)
        latency_headroom = _headroom_upper(endpoint.metrics.latency_p95_ms, constraints.latency_targets.end_to_end_p95_ms)
        ttft_headroom = _headroom_upper(endpoint.metrics.time_to_first_token_p95_ms, constraints.latency_targets.time_to_first_token_p95_ms)
        cost_delta = _pct_delta(cost, recommended_cost)
        latency_delta = _pct_delta(endpoint.metrics.latency_p95_ms, fastest_latency)
        rows.append(
            DecisionTableRow(
                endpoint_id=endpoint.endpoint_id,
                status=endpoint.benchmark_status,
                score=round(score, 4),
                latency_p95_ms=endpoint.metrics.latency_p95_ms,
                time_to_first_token_p95_ms=endpoint.metrics.time_to_first_token_p95_ms,
                inter_token_latency_p95_ms=endpoint.metrics.inter_token_latency_p95_ms,
                requests_per_second=endpoint.metrics.requests_per_second,
                output_tokens_per_second=endpoint.metrics.output_tokens_per_second,
                error_rate_pct=endpoint.metrics.error_rate_pct,
                timeout_rate_pct=endpoint.metrics.timeout_rate_pct,
                estimated_cost_per_1k_requests=endpoint.economics.get("estimated_cost_per_1k_requests"),
                latency_headroom_ms=latency_headroom,
                ttft_headroom_ms=ttft_headroom,
                cost_delta_vs_recommended_pct=cost_delta,
                latency_delta_vs_fastest_pct=latency_delta,
                data_location_status=_data_location_status(endpoint),
                primary_strength=_primary_strength(endpoint, results.endpoints, cost, fastest_latency),
                primary_risk=_primary_risk(endpoint, cost, recommended_cost, fastest_latency),
                why_not_selected=_why_not_selected(endpoint, recommended_endpoint_id, objective),
                summary=_row_summary(endpoint),
            )
        )
    return sorted(rows, key=lambda row: (-row.score, row.endpoint_id))


def _choose_pass_endpoint(endpoints: list[EndpointResult], objective: str, constraints: Constraints) -> EndpointResult:
    if objective == "lowest_latency":
        return sorted(endpoints, key=lambda e: (_none_high(e.metrics.latency_p95_ms), e.metrics.error_rate_pct, e.endpoint_id))[0]
    if objective == "highest_throughput":
        return sorted(endpoints, key=lambda e: (-_none_low(e.metrics.requests_per_second), _none_high(e.metrics.latency_p95_ms), e.endpoint_id))[0]
    if objective == "lowest_unit_cost":
        with_cost = [endpoint for endpoint in endpoints if _known_float(endpoint.economics.get("estimated_cost_per_1k_requests")) is not None]
        source = with_cost if with_cost else endpoints
        return sorted(source, key=lambda e: (_none_high(_known_float(e.economics.get("estimated_cost_per_1k_requests"))), _none_high(e.metrics.latency_p95_ms), e.endpoint_id))[0]
    rows_by_id = {row.endpoint_id: row for row in _decision_rows(BenchmarkResults(run_id="x", workload_id="x", started_at="x", finished_at="x", mode="MEASURED_HTTP", config={}, endpoints=endpoints), constraints)}
    return sorted(
        endpoints,
        key=lambda e: (
            -rows_by_id[e.endpoint_id].score,
            _none_high(e.metrics.latency_p95_ms),
            e.metrics.error_rate_pct,
            _none_high(_known_float(e.economics.get("estimated_cost_per_1k_requests"))),
            -_none_low(e.metrics.output_tokens_per_second),
            e.endpoint_id,
        ),
    )[0]


def _recommend_reason_codes(pass_results: list[EndpointResult], recommended: EndpointResult, objective: str) -> list[str]:
    codes = ["DATA_LOCATION_DECLARED_ALLOWED"]
    if objective == "lowest_latency":
        codes.append("RECOMMENDED_LOWEST_LATENCY")
    elif objective == "highest_throughput":
        codes.append("RECOMMENDED_HIGHEST_THROUGHPUT")
    elif objective == "lowest_unit_cost":
        codes.append("RECOMMENDED_LOWEST_UNIT_COST")
    else:
        codes.append("RECOMMENDED_BALANCED_SCORE")
    if recommended.metrics.latency_p95_ms is not None and all(
        other.endpoint_id == recommended.endpoint_id
        or other.metrics.latency_p95_ms is None
        or recommended.metrics.latency_p95_ms <= other.metrics.latency_p95_ms
        for other in pass_results
    ):
        codes.append("LOWER_P95_THAN_PEERS")
    rec_cost = _known_float(recommended.economics.get("estimated_cost_per_1k_requests"))
    if rec_cost is not None and all(
        other.endpoint_id == recommended.endpoint_id
        or _known_float(other.economics.get("estimated_cost_per_1k_requests")) is None
        or rec_cost <= _known_float(other.economics.get("estimated_cost_per_1k_requests"))
        for other in pass_results
    ):
        codes.append("LOWER_COST_THAN_PEERS")
    return codes


def _confidence(results: BenchmarkResults, warnings: list[str], config: dict[str, Any]) -> str:
    successes = [endpoint.metrics.success_count for endpoint in results.endpoints if endpoint.benchmark_status in {"PASS", "REVIEW"}]
    if not successes:
        return "LOW"
    min_successes = min(successes)
    high_min = int(config.get("minimum_successful_requests_high_confidence", 50))
    medium_min = int(config.get("minimum_successful_requests_medium_confidence", 20))
    if min_successes >= high_min and not warnings:
        return "HIGH"
    if min_successes >= medium_min:
        return "MEDIUM"
    return "LOW"


def _input_quality(results: BenchmarkResults) -> dict[str, Any]:
    endpoints = results.endpoints
    comparable = [endpoint for endpoint in endpoints if endpoint.benchmark_status in {"PASS", "REVIEW", "FAIL"}]
    successful_counts = [endpoint.metrics.success_count for endpoint in comparable]
    economics_known = [
        endpoint for endpoint in comparable if _known_float(endpoint.economics.get("estimated_cost_per_1k_requests")) is not None
    ]
    token_summaries = [endpoint.metrics.token_count_source_summary or "" for endpoint in comparable]
    exact_token_endpoints = [summary for summary in token_summaries if "EXACT_FROM_RESPONSE" in summary]
    declared_locations = [endpoint for endpoint in endpoints if endpoint.declared_location is not None]
    warnings: list[str] = []
    min_success = min(successful_counts) if successful_counts else 0
    if min_success < 20:
        warnings.append("SMALL_SAMPLE_SIZE")
    if len(exact_token_endpoints) < len(comparable):
        warnings.append("TOKEN_COUNTS_ESTIMATED")
    if len(economics_known) < len(comparable):
        warnings.append("UNIT_ECONOMICS_MISSING")
    if len(declared_locations) < len(endpoints):
        warnings.append("DECLARED_LOCATION_MISSING")
    score = 100
    score -= 25 if min_success < 5 else 15 if min_success < 20 else 0
    score -= 15 if "TOKEN_COUNTS_ESTIMATED" in warnings else 0
    score -= 15 if "UNIT_ECONOMICS_MISSING" in warnings else 0
    score -= 20 if "DECLARED_LOCATION_MISSING" in warnings else 0
    return {
        "score": max(0, score),
        "minimum_successful_requests": min_success,
        "endpoint_count": len(endpoints),
        "comparable_endpoint_count": len(comparable),
        "economics_known_endpoint_count": len(economics_known),
        "exact_token_usage_endpoint_count": len(exact_token_endpoints),
        "declared_location_endpoint_count": len(declared_locations),
        "warnings": _unique(warnings),
    }


def _sensitivity_analysis(pass_results: list[EndpointResult], recommended: EndpointResult | None) -> list[dict[str, Any]]:
    if not pass_results:
        return []
    baseline = recommended.endpoint_id if recommended else None
    scenarios = [
        ("latency_priority", _choose_by_latency(pass_results)),
        ("throughput_priority", _choose_by_throughput(pass_results)),
        ("economics_priority", _choose_by_cost(pass_results)),
    ]
    return [
        {
            "scenario": scenario,
            "winner_endpoint_id": winner.endpoint_id if winner else None,
            "changes_recommendation": bool(baseline and winner and winner.endpoint_id != baseline),
        }
        for scenario, winner in scenarios
    ]


def _placement_summary(
    status: str,
    recommended: EndpointResult | None,
    rows: list[DecisionTableRow],
    objective: str,
    constraints: Constraints,
) -> dict[str, Any]:
    if not recommended:
        return {
            "decision": "No review-only placement candidate can be selected from this run.",
            "why": _non_recommended_reasons(rows),
            "tradeoff": "Human review is required before placement discussion.",
            "human_review_focus": _human_review_focus(rows),
        }
    rec_row = next((row for row in rows if row.endpoint_id == recommended.endpoint_id), None)
    why = [
        "The endpoint passed declared eligibility and benchmark targets in this run.",
        f"The recommendation objective is {objective}.",
    ]
    if rec_row and rec_row.primary_strength:
        why.append(rec_row.primary_strength)
    if rec_row and rec_row.latency_headroom_ms is not None and rec_row.latency_headroom_ms > 0:
        why.append(f"It has {rec_row.latency_headroom_ms:.1f} ms of p95 latency headroom against the configured target.")
    tradeoff = _tradeoff_text(recommended.endpoint_id, rows)
    return {
        "decision": f"{recommended.endpoint_id} is the review-only placement candidate for this workload.",
        "why": why,
        "tradeoff": tradeoff,
        "human_review_focus": _human_review_focus(rows),
    }


def _business_impact(
    results: BenchmarkResults,
    recommended: EndpointResult | None,
    rows: list[DecisionTableRow],
    constraints: Constraints,
) -> dict[str, Any]:
    if not recommended:
        return {
            "decision_type": "no placement candidate",
            "review_value": "The run identifies blockers or missing evidence before endpoint integration work proceeds.",
            "unit_economics_context": "No endpoint was selected, so unit economics are review context only.",
            "passing_endpoint_count": len([row for row in rows if row.status == "PASS"]),
        }
    pass_rows = [row for row in rows if row.status == "PASS"]
    fastest = min(pass_rows, key=lambda row: _none_high(row.latency_p95_ms), default=None)
    cheapest = min(pass_rows, key=lambda row: _none_high(_known_float(row.estimated_cost_per_1k_requests)), default=None)
    rec_row = next((row for row in rows if row.endpoint_id == recommended.endpoint_id), None)
    rec_cost = _known_float(rec_row.estimated_cost_per_1k_requests) if rec_row else None
    fastest_cost = _known_float(fastest.estimated_cost_per_1k_requests) if fastest else None
    cheapest_cost = _known_float(cheapest.estimated_cost_per_1k_requests) if cheapest else None
    cost_delta = None
    if rec_cost is not None and fastest_cost is not None:
        cost_delta = round(rec_cost - fastest_cost, 6)
    latency_delta = None
    latency_delta_pct = None
    if rec_row and fastest and rec_row.latency_p95_ms is not None and fastest.latency_p95_ms is not None:
        latency_delta = round(rec_row.latency_p95_ms - fastest.latency_p95_ms, 4)
        latency_delta_pct = _pct_delta(rec_row.latency_p95_ms, fastest.latency_p95_ms)
    cost_delta_vs_cheapest_pct = _pct_delta(rec_cost, cheapest_cost)
    sensitivity_changes = any(row.get("changes_recommendation") for row in _sensitivity_analysis([endpoint for endpoint in results.endpoints if endpoint.benchmark_status == "PASS"], recommended))
    decision_type = "balanced placement candidate"
    if cheapest and recommended.endpoint_id == cheapest.endpoint_id and fastest and recommended.endpoint_id != fastest.endpoint_id:
        decision_type = "cost-saving within configured latency constraints"
    elif fastest and recommended.endpoint_id == fastest.endpoint_id:
        decision_type = "latency-led placement candidate"
    economics_known = sum(1 for row in pass_rows if _known_float(row.estimated_cost_per_1k_requests) is not None)
    if economics_known == len(pass_rows):
        economics_context = "All passing endpoints include comparable user-supplied unit economics."
    elif economics_known:
        economics_context = "Some passing endpoints are missing user-supplied unit economics, so cost comparisons need review."
    else:
        economics_context = "No passing endpoint has known user-supplied unit economics."
    return {
        "decision_type": decision_type,
        "fastest_endpoint_id": fastest.endpoint_id if fastest else None,
        "cheapest_endpoint_id": cheapest.endpoint_id if cheapest else None,
        "cost_delta_per_1k_requests_vs_fastest": cost_delta,
        "selected_cost_delta_vs_cheapest_pct": cost_delta_vs_cheapest_pct,
        "latency_delta_ms_vs_fastest": latency_delta,
        "selected_latency_delta_vs_fastest_pct": latency_delta_pct,
        "sensitivity_changes_recommendation": bool(sensitivity_changes),
        "passing_endpoint_count": len(pass_rows),
        "unit_economics_context": economics_context,
        "review_value": "Eligible endpoints compared under workload-specific latency, throughput, reliability, declared-location, and user-supplied economics constraints.",
    }


def _headroom_upper(value: float | None, target: float | None) -> float | None:
    if value is None or target is None:
        return None
    return round(target - value, 4)


def _pct_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or baseline == 0:
        return None
    return round((value - baseline) / baseline * 100.0, 3)


def _primary_strength(endpoint: EndpointResult, endpoints: list[EndpointResult], cost: float | None, fastest_latency: float | None) -> str:
    pass_endpoints = [item for item in endpoints if item.benchmark_status == "PASS"]
    cheapest = min((_known_float(item.economics.get("estimated_cost_per_1k_requests")) for item in pass_endpoints), default=None)
    best_throughput = max((item.metrics.requests_per_second for item in pass_endpoints if item.metrics.requests_per_second is not None), default=None)
    strengths: list[str] = []
    if fastest_latency is not None and endpoint.metrics.latency_p95_ms == fastest_latency:
        strengths.append("fastest p95 latency among passing endpoints")
    if cost is not None and cheapest is not None and cost == cheapest:
        strengths.append("lowest estimated unit cost among passing endpoints")
    if best_throughput is not None and endpoint.metrics.requests_per_second == best_throughput:
        strengths.append("highest observed request throughput among passing endpoints")
    if endpoint.benchmark_status == "PASS" and not strengths:
        strengths.append("passed all configured benchmark targets")
    if endpoint.benchmark_status == "INELIGIBLE":
        strengths.append("none for this workload because eligibility failed")
    return "; ".join(strengths) if strengths else "requires review"


def _primary_risk(endpoint: EndpointResult, cost: float | None, recommended_cost: float | None, fastest_latency: float | None) -> str:
    actionable_warnings = [warning for warning in endpoint.warnings if warning not in {"REVIEW_ONLY_OUTPUT", "BENCHMARK_IS_NOT_CAPACITY_TEST"}]
    if endpoint.benchmark_status == "INELIGIBLE":
        return "Eligibility constraint failed before benchmark."
    if endpoint.benchmark_status == "FAIL":
        return "One or more required benchmark targets were missed."
    if endpoint.benchmark_status == "REVIEW":
        return "Evidence is incomplete or near a configured target."
    if actionable_warnings:
        return f"Warnings require review: {', '.join(actionable_warnings)}."
    if recommended_cost is not None and cost is not None and cost > recommended_cost:
        return "Higher estimated unit cost than the recommended endpoint."
    if fastest_latency is not None and endpoint.metrics.latency_p95_ms is not None and endpoint.metrics.latency_p95_ms > fastest_latency:
        return "Slower p95 latency than the fastest passing endpoint."
    return "No specific risk surfaced by this micro-benchmark."


def _why_not_selected(endpoint: EndpointResult, recommended_endpoint_id: str | None, objective: str) -> str | None:
    if recommended_endpoint_id is None:
        return "No endpoint was selected from this run."
    if endpoint.endpoint_id == recommended_endpoint_id:
        return "Selected by the configured recommendation objective."
    if endpoint.benchmark_status == "INELIGIBLE":
        return "Not selected because eligibility failed before benchmark."
    if endpoint.benchmark_status == "FAIL":
        return "Not selected because a required target was missed."
    if endpoint.benchmark_status == "REVIEW":
        return "Not selected because it requires human review before placement."
    if objective == "lowest_latency":
        return "Not selected because another passing endpoint had lower p95 latency."
    if objective == "highest_throughput":
        return "Not selected because another passing endpoint had higher observed throughput."
    if objective == "lowest_unit_cost":
        return "Not selected because another passing endpoint had lower estimated unit cost."
    return "Not selected because its balanced score was lower under the configured weights."


def _tradeoff_text(recommended_endpoint_id: str, rows: list[DecisionTableRow]) -> str:
    rec = next((row for row in rows if row.endpoint_id == recommended_endpoint_id), None)
    fastest = min((row for row in rows if row.status == "PASS"), key=lambda row: _none_high(row.latency_p95_ms), default=None)
    cheapest = min((row for row in rows if row.status == "PASS"), key=lambda row: _none_high(_known_float(row.estimated_cost_per_1k_requests)), default=None)
    if rec and fastest and rec.endpoint_id != fastest.endpoint_id and cheapest and rec.endpoint_id == cheapest.endpoint_id:
        return "The selected endpoint trades higher p95 latency for lower estimated unit cost while remaining within configured targets."
    if rec and fastest and rec.endpoint_id == fastest.endpoint_id:
        return "The selected endpoint prioritizes measured p95 latency and throughput over lower-cost alternatives."
    return "The selected endpoint has the strongest score under the configured placement objective."


def _human_review_focus(rows: list[DecisionTableRow]) -> list[str]:
    focus = [
        "Repeat with production-like prompt shapes before production placement.",
        "Confirm endpoint capacity, support terms, and data-handling commitments.",
    ]
    if any(row.data_location_status != "PASS" for row in rows):
        focus.append("Resolve declared data-location or operator-control gaps.")
    if any(row.estimated_cost_per_1k_requests in {None, "UNKNOWN"} for row in rows):
        focus.append("Provide user-supplied rate cards for comparable economics.")
    if any(row.status in {"REVIEW", "FAIL", "INELIGIBLE"} for row in rows):
        focus.append("Review blocked or marginal endpoints before considering them for placement.")
    return focus


def _non_recommended_reasons(rows: list[DecisionTableRow]) -> list[str]:
    if not rows:
        return ["No endpoint evidence was available."]
    reasons = []
    for row in rows[:5]:
        if row.why_not_selected:
            reasons.append(f"{row.endpoint_id}: {row.why_not_selected}")
    return reasons or ["No passing endpoint was available."]


def _choose_by_latency(endpoints: list[EndpointResult]) -> EndpointResult | None:
    if not endpoints:
        return None
    return sorted(endpoints, key=lambda e: (_none_high(e.metrics.latency_p95_ms), e.endpoint_id))[0]


def _choose_by_throughput(endpoints: list[EndpointResult]) -> EndpointResult | None:
    if not endpoints:
        return None
    return sorted(endpoints, key=lambda e: (-_none_low(e.metrics.requests_per_second), e.endpoint_id))[0]


def _choose_by_cost(endpoints: list[EndpointResult]) -> EndpointResult | None:
    with_cost = [endpoint for endpoint in endpoints if _known_float(endpoint.economics.get("estimated_cost_per_1k_requests")) is not None]
    source = with_cost if with_cost else endpoints
    if not source:
        return None
    return sorted(source, key=lambda e: (_none_high(_known_float(e.economics.get("estimated_cost_per_1k_requests"))), e.endpoint_id))[0]


def _summary_text(status: str, endpoint: EndpointResult | None, constraints: Constraints) -> str:
    if status == "RECOMMENDED" and endpoint:
        return (
            f"Review-only recommendation: {endpoint.endpoint_id} is the best measured candidate for this workload because it satisfies "
            "the declared data-location constraint and benchmark targets in this run. Economics are based on user-supplied rate-card values."
        )
    if status == "NO_CLEAR_WINNER_REVIEW_REQUIRED":
        return "Review-only recommendation: no passing endpoint was found, but at least one candidate needs human review before a placement decision."
    if status == "NO_ENDPOINT_MEETS_CONSTRAINTS":
        return "Review-only recommendation: no candidate endpoint met the declared constraints in this run."
    return "Review-only recommendation: insufficient benchmark data is available."


def _row_summary(endpoint: EndpointResult) -> str:
    if endpoint.benchmark_status == "PASS":
        return "Meets declared location and benchmark targets in this run."
    if endpoint.benchmark_status == "REVIEW":
        return "Requires review because evidence is incomplete or a target was marginal."
    if endpoint.benchmark_status == "INELIGIBLE":
        return "Excluded before benchmark because an eligibility constraint failed."
    if endpoint.benchmark_status == "ELIGIBLE_NOT_RUN":
        return "Eligible before benchmark, but no measured run was performed."
    return "Missed a required benchmark target or could not complete the benchmark."


def _data_location_status(endpoint: EndpointResult) -> str:
    if "DECLARED_LOCATION_NOT_ALLOWED" in endpoint.reason_codes or "DECLARED_LOCATION_MISSING" in endpoint.reason_codes and endpoint.eligibility_status == "INELIGIBLE":
        return "FAIL"
    if "DECLARED_LOCATION_ALLOWED" in endpoint.reason_codes:
        return "PASS"
    return "UNKNOWN"


def _known_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "UNKNOWN":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _none_high(value: float | None) -> float:
    return float("inf") if value is None else value


def _none_low(value: float | None) -> float:
    return float("-inf") if value is None else value


def _unique(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out
