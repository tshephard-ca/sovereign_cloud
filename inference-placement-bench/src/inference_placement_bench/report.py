from __future__ import annotations

from pathlib import Path

from .models import RecommendationOutput


def render_markdown_report(recommendation: RecommendationOutput) -> str:
    rows = recommendation.decision_table
    summary = recommendation.placement_summary or {}
    impact = recommendation.business_impact or {}
    lines: list[str] = []
    lines.append("# Inference Placement Decision Review")
    lines.append("")
    lines.append(
        "Review-only output. This is a workload-specific placement preflight, not production approval, "
        "routing, capacity reservation, procurement approval, or compliance proof."
    )
    lines.append("")
    lines.append("## Placement Decision")
    lines.append("")
    lines.append(f"- Workload ID: `{recommendation.workload_id}`")
    lines.append(f"- Constraint ID: `{recommendation.constraint_id}`")
    lines.append(f"- Recommendation status: `{recommendation.recommendation_status}`")
    lines.append(f"- Recommended endpoint: `{recommendation.recommended_endpoint_id or 'none'}`")
    lines.append(f"- Objective: `{recommendation.objective}`")
    lines.append(f"- Confidence: `{recommendation.confidence}`")
    lines.append(f"- Decision: {summary.get('decision', recommendation.business_summary.get('text', 'No placement decision available.'))}")
    lines.append("")
    lines.append("## Why This Endpoint Won" if recommendation.recommended_endpoint_id else "## Why This Outcome")
    lines.append("")
    for item in summary.get("why", []) or [recommendation.business_summary.get("text", "No summary available.")]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Business Impact")
    lines.append("")
    lines.append(f"- Decision type: {fmt(impact.get('decision_type'))}")
    lines.append(f"- Review value: {fmt(impact.get('review_value'))}")
    lines.append(f"- Unit economics context: {fmt(impact.get('unit_economics_context'))}")
    lines.append(f"- Fastest endpoint: `{fmt(impact.get('fastest_endpoint_id'))}`")
    lines.append(f"- Cheapest endpoint with known economics: `{fmt(impact.get('cheapest_endpoint_id'))}`")
    lines.append(f"- Selected vs fastest latency delta: {fmt(impact.get('selected_latency_delta_vs_fastest_pct'))}%")
    lines.append(f"- Selected vs cheapest cost delta: {fmt(impact.get('selected_cost_delta_vs_cheapest_pct'))}%")
    lines.append(f"- Sensitivity changes recommendation: `{fmt(impact.get('sensitivity_changes_recommendation'))}`")
    lines.append("")
    lines.append("## Tradeoff Summary")
    lines.append("")
    lines.append(summary.get("tradeoff", "No tradeoff summary available."))
    lines.append("")
    lines.append("## Sensitivity And Decision Stability")
    lines.append("")
    if recommendation.sensitivity_analysis:
        lines.append("| Scenario | Winner | Changes recommendation |")
        lines.append("| --- | --- | --- |")
        for row in recommendation.sensitivity_analysis:
            lines.append(
                f"| `{row.get('scenario')}` | `{row.get('winner_endpoint_id')}` | `{row.get('changes_recommendation')}` |"
            )
    else:
        lines.append("- No passing endpoint sensitivity scenarios were available.")
    lines.append("")
    lines.append("## Endpoint Comparison")
    lines.append("")
    lines.append(
        "| Endpoint | Status | Score | p95 latency ms | latency headroom ms | requests/sec | cost per 1k requests | "
        "Cost delta vs selected | Strength | Risk | Selection note |"
    )
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |")
    for row in rows:
        lines.append(
            f"| `{row.endpoint_id}` | `{row.status}` | {fmt(row.score)} | {fmt(row.latency_p95_ms)} | "
            f"{fmt(row.latency_headroom_ms)} | {fmt(row.requests_per_second)} | {fmt(row.estimated_cost_per_1k_requests)} | "
            f"{fmt_pct(row.cost_delta_vs_recommended_pct)} | {_cell(row.primary_strength)} | {_cell(row.primary_risk)} | {_cell(row.why_not_selected)} |"
        )
    lines.append("")
    lines.append("## Data-location Constraint Result")
    lines.append("")
    lines.append("Location checks use declared endpoint metadata only. The tool does not geolocate traffic or verify data residency.")
    lines.append("")
    lines.append("| Endpoint | Data-location status | Summary |")
    lines.append("| --- | --- | --- |")
    for row in rows:
        lines.append(f"| `{row.endpoint_id}` | `{row.data_location_status}` | {_cell(row.summary)} |")
    lines.append("")
    lines.append("## Reliability And Token Evidence")
    lines.append("")
    lines.append("| Endpoint | error rate % | timeout rate % | output tokens/sec | TTFT p95 ms | inter-token p95 ms |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in rows:
        lines.append(
            f"| `{row.endpoint_id}` | {fmt(row.error_rate_pct)} | {fmt(row.timeout_rate_pct)} | "
            f"{fmt(row.output_tokens_per_second)} | {fmt(row.time_to_first_token_p95_ms)} | {fmt(row.inter_token_latency_p95_ms)} |"
        )
    lines.append("")
    lines.append("## Risk, Blockers, And Caveats")
    lines.append("")
    lines.append("### Reason Codes")
    for code in recommendation.reason_codes or ["none"]:
        lines.append(f"- `{code}`")
    lines.append("")
    lines.append("### Warnings")
    for warning in recommendation.warnings or ["none"]:
        lines.append(f"- `{warning}`")
    lines.append("")
    lines.append("### Caveats")
    for caveat in recommendation.caveats:
        lines.append(f"- {caveat}")
    lines.append("")
    lines.append("## Recommended Human Questions")
    lines.append("")
    for question in next_questions(recommendation):
        lines.append(f"- {question}")
    lines.append("")
    lines.append("## Raw Benchmark Appendix")
    lines.append("")
    lines.append("### Input Quality")
    if recommendation.input_quality:
        for key, value in recommendation.input_quality.items():
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- UNKNOWN")
    lines.append("")
    lines.append("### Raw Decision Rows")
    lines.append("")
    lines.append("| Endpoint | p95 latency ms | TTFT p95 ms | inter-token p95 ms | requests/sec | output tokens/sec | error % | timeout % |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in rows:
        lines.append(
            f"| `{row.endpoint_id}` | {fmt(row.latency_p95_ms)} | {fmt(row.time_to_first_token_p95_ms)} | "
            f"{fmt(row.inter_token_latency_p95_ms)} | {fmt(row.requests_per_second)} | "
            f"{fmt(row.output_tokens_per_second)} | {fmt(row.error_rate_pct)} | {fmt(row.timeout_rate_pct)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_executive_summary(recommendation: RecommendationOutput) -> str:
    summary = recommendation.placement_summary or {}
    impact = recommendation.business_impact or {}
    lines = [
        "# Executive Summary",
        "",
        "Review-only inference placement preflight. This is not production approval, capacity certification, routing, procurement approval, or compliance proof.",
        "",
        f"- Status: `{recommendation.recommendation_status}`",
        f"- Recommended endpoint: `{recommendation.recommended_endpoint_id or 'none'}`",
        f"- Confidence: `{recommendation.confidence}`",
        f"- Decision: {summary.get('decision', recommendation.business_summary.get('text', 'No decision available.'))}",
        f"- Tradeoff: {summary.get('tradeoff', 'No tradeoff summary available.')}",
        "",
        "## Business Impact",
        f"- Decision type: {fmt(impact.get('decision_type'))}",
        f"- Review value: {fmt(impact.get('review_value'))}",
        f"- Unit economics context: {fmt(impact.get('unit_economics_context'))}",
        f"- Sensitivity changes recommendation: `{fmt(impact.get('sensitivity_changes_recommendation'))}`",
    ]
    lines.extend(["", "## Human Review Focus"])
    for item in summary.get("human_review_focus", []) or next_questions(recommendation):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_report(recommendation: RecommendationOutput, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown_report(recommendation), encoding="utf-8")


def fmt(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def fmt_pct(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    return f"{fmt(value)}%"


def _cell(value: object) -> str:
    text = fmt(value)
    return text.replace("|", "\\|")


def next_questions(recommendation: RecommendationOutput) -> list[str]:
    questions: list[str] = []
    codes = set(recommendation.reason_codes)
    warnings = set(recommendation.warnings)
    if "DECLARED_LOCATION_MISSING" in codes:
        questions.append("Can the endpoint owner provide a declared data zone and operator-control description?")
    if "DECLARED_LOCATION_NOT_ALLOWED" in codes:
        questions.append("Is this workload allowed to run outside the requested data zone, or should this endpoint be excluded?")
    if "STREAMING_REQUIRED_NOT_SUPPORTED" in codes:
        questions.append("Is streaming required for the user experience, or is non-streaming acceptable?")
    if "LATENCY_TARGET_MISSED" in codes:
        questions.append("Is the p95 latency target a hard user-experience requirement or a review threshold?")
    if "TTFT_TARGET_MISSED" in codes:
        questions.append("Does perceived responsiveness depend on time to first token for this workload?")
    if "INTER_TOKEN_LATENCY_TARGET_MISSED" in codes:
        questions.append("Does the user experience depend on smooth token streaming after the first token?")
    if "THROUGHPUT_TARGET_MISSED" in codes:
        questions.append("Is this a single-user latency workload or a concurrent production workload needing capacity testing?")
    if "UNIT_ECONOMICS_MISSING" in warnings:
        questions.append("Can the endpoint owner provide a rate card for input tokens, output tokens, and per-request charges?")
    if "TOKEN_COUNTS_ESTIMATED" in warnings:
        questions.append("Can the endpoint return usage metrics so economics are not based on token estimates?")
    if "SMALL_SAMPLE_SIZE" in warnings:
        questions.append("Should the run be repeated with more prompts and a longer measurement window?")
    if "HIGH_ERROR_RATE_NEAR_THRESHOLD" in warnings:
        questions.append("Were errors caused by endpoint throttling, auth, payload shape, timeout, or transient platform issues?")
    if "NO_CLEAR_WINNER" in codes:
        questions.append("Which matters more for this workload: p95 latency, unit economics, throughput, or location policy?")
    if not questions:
        questions.append("Should this micro-benchmark be repeated with production-like prompt shapes before placement review?")
    return questions
