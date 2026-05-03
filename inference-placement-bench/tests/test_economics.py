from __future__ import annotations

from inference_placement_bench.economics import compute_economics
from inference_placement_bench.models import AggregateMetrics, UnitEconomics


def test_economics_unknown_when_no_rate_card_supplied():
    economics, reasons, warnings = compute_economics(None, AggregateMetrics(success_count=1), 1, [])
    assert economics["estimated_cost_per_1k_requests"] == "UNKNOWN"
    assert "ECONOMICS_UNKNOWN" in reasons
    assert "UNIT_ECONOMICS_MISSING" in warnings


def test_economics_computed_from_user_supplied_rate_card():
    metrics = AggregateMetrics(input_tokens_total=1_000_000, output_tokens_total=1_000_000)
    economics, reasons, _ = compute_economics(
        UnitEconomics(currency="CAD", input_per_1m_tokens=1, output_per_1m_tokens=2, per_1k_requests=3, per_request=0.1),
        metrics,
        1000,
        ["EXACT_FROM_RESPONSE"],
    )
    assert economics["estimated_cost_for_benchmark_run"] == 106.0
    assert "USER_SUPPLIED_RATE_CARD" in reasons


def test_cost_calculation_flags_estimated_token_usage():
    metrics = AggregateMetrics(input_tokens_total=100, output_tokens_total=100)
    _, reasons, warnings = compute_economics(
        UnitEconomics(currency="CAD", input_per_1m_tokens=1, output_per_1m_tokens=2),
        metrics,
        1,
        ["HEURISTIC_ESTIMATE"],
    )
    assert "COST_USES_ESTIMATED_TOKENS" in reasons
    assert "TOKEN_COUNTS_ESTIMATED" in warnings
