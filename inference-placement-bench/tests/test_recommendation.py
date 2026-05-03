from __future__ import annotations

from inference_placement_bench.models import BenchmarkResults
from inference_placement_bench.recommendation import build_recommendation

from conftest import make_constraints, make_results_with_endpoint


def combine(*results):
    first = results[0]
    return BenchmarkResults(
        run_id="run",
        workload_id=first.workload_id,
        started_at=first.started_at,
        finished_at=first.finished_at,
        mode="MEASURED_HTTP",
        config={},
        endpoints=[endpoint for result in results for endpoint in result.endpoints],
    )


def test_recommendation_chooses_lowest_latency_objective_correctly():
    results = combine(
        make_results_with_endpoint(endpoint_id="slow", status="PASS", latency=200, cost=1),
        make_results_with_endpoint(endpoint_id="fast", status="PASS", latency=100, cost=2),
    )
    recommendation = build_recommendation(results, make_constraints(objective="lowest_latency"))
    assert recommendation.recommended_endpoint_id == "fast"


def test_recommendation_chooses_lowest_unit_cost_objective_correctly_when_known():
    results = combine(
        make_results_with_endpoint(endpoint_id="costly", status="PASS", latency=100, cost=3),
        make_results_with_endpoint(endpoint_id="lower_cost", status="PASS", latency=120, cost=1),
    )
    recommendation = build_recommendation(results, make_constraints(objective="lowest_unit_cost"))
    assert recommendation.recommended_endpoint_id == "lower_cost"


def test_recommendation_explains_business_tradeoff_and_decision_rows():
    results = combine(
        make_results_with_endpoint(endpoint_id="fast", status="PASS", latency=100, cost=3),
        make_results_with_endpoint(endpoint_id="cheap", status="PASS", latency=180, cost=1),
    )
    recommendation = build_recommendation(results, make_constraints(objective="balanced", latency_target=500))
    assert recommendation.placement_summary["decision"].startswith("cheap")
    assert recommendation.business_impact["decision_type"] == "cost-saving within configured latency constraints"
    cheap = next(row for row in recommendation.decision_table if row.endpoint_id == "cheap")
    fast = next(row for row in recommendation.decision_table if row.endpoint_id == "fast")
    assert cheap.latency_headroom_ms == 320
    assert cheap.why_not_selected == "Selected by the configured recommendation objective."
    assert fast.why_not_selected is not None
    assert fast.cost_delta_vs_recommended_pct == 200.0


def test_recommendation_refuses_location_violating_endpoint_even_if_fastest():
    results = combine(
        make_results_with_endpoint(endpoint_id="blocked", status="INELIGIBLE", latency=10, reason_codes=["DECLARED_LOCATION_NOT_ALLOWED"]),
        make_results_with_endpoint(endpoint_id="allowed", status="PASS", latency=100, reason_codes=["DECLARED_LOCATION_ALLOWED"]),
    )
    recommendation = build_recommendation(results, make_constraints(objective="lowest_latency"))
    assert recommendation.recommended_endpoint_id == "allowed"


def test_no_passing_endpoints_yields_no_endpoint_meets_constraints():
    recommendation = build_recommendation(
        make_results_with_endpoint(endpoint_id="failed", status="FAIL", latency=2000),
        make_constraints(),
    )
    assert recommendation.recommendation_status == "NO_ENDPOINT_MEETS_CONSTRAINTS"


def test_review_only_candidates_yield_no_clear_winner_review_required():
    recommendation = build_recommendation(
        make_results_with_endpoint(endpoint_id="review", status="REVIEW", latency=100),
        make_constraints(),
    )
    assert recommendation.recommendation_status == "NO_CLEAR_WINNER_REVIEW_REQUIRED"
