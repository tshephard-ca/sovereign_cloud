from __future__ import annotations

from typing import Any

from .models import AggregateMetrics, UnitEconomics


UNKNOWN = "UNKNOWN"


def compute_economics(
    rate_card: UnitEconomics | None,
    metrics: AggregateMetrics,
    successful_requests: int,
    token_sources: list[str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    if rate_card is None:
        return (
            {
                "currency": None,
                "estimated_cost_per_1k_requests": UNKNOWN,
                "estimated_cost_per_1m_input_tokens": UNKNOWN,
                "estimated_cost_per_1m_output_tokens": UNKNOWN,
                "estimated_cost_for_benchmark_run": UNKNOWN,
                "cost_basis": UNKNOWN,
            },
            ["ECONOMICS_UNKNOWN"],
            ["UNIT_ECONOMICS_MISSING"],
        )

    input_tokens_total = metrics.input_tokens_total or 0
    output_tokens_total = metrics.output_tokens_total or 0
    input_rate = rate_card.input_per_1m_tokens or 0.0
    output_rate = rate_card.output_per_1m_tokens or 0.0
    per_1k_requests = rate_card.per_1k_requests or 0.0
    per_request = rate_card.per_request or 0.0
    cost = (
        input_tokens_total / 1_000_000 * input_rate
        + output_tokens_total / 1_000_000 * output_rate
        + successful_requests / 1000 * per_1k_requests
        + successful_requests * per_request
    )
    per_1k = cost / successful_requests * 1000 if successful_requests else UNKNOWN
    per_1m_output = cost / output_tokens_total * 1_000_000 if output_tokens_total else UNKNOWN
    reasons = ["ECONOMICS_PRESENT", "USER_SUPPLIED_RATE_CARD"]
    warnings: list[str] = []
    if any(source != "EXACT_FROM_RESPONSE" for source in token_sources):
        reasons.append("COST_USES_ESTIMATED_TOKENS")
        warnings.append("TOKEN_COUNTS_ESTIMATED")
    return (
        {
            "currency": rate_card.currency,
            "estimated_cost_per_1k_requests": _round_or_unknown(per_1k),
            "estimated_cost_per_1m_input_tokens": rate_card.input_per_1m_tokens if rate_card.input_per_1m_tokens is not None else UNKNOWN,
            "estimated_cost_per_1m_output_tokens": _round_or_unknown(per_1m_output),
            "estimated_cost_for_benchmark_run": round(cost, 8),
            "cost_basis": "USER_SUPPLIED_RATE_CARD",
            "monthly_commit": rate_card.monthly_commit if rate_card.monthly_commit is not None else rate_card.minimum_monthly_commit,
            "notes": rate_card.notes,
        },
        reasons,
        warnings,
    )


def _round_or_unknown(value: float | str) -> float | str:
    if isinstance(value, str):
        return value
    return round(value, 8)
