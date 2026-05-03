# Output Contract

The primary output is a decision bundle.

## Decision Bundle Files

- `executive_summary.md`: short business-facing decision summary.
- `recommendation.md`: decision-first Markdown review package.
- `recommendation.json`: structured recommendation output.
- `results.json`: copied benchmark result for bundle handoff.
- `input_hashes.json`: SHA-256 hashes of input-bundle files.
- `bundle_manifest.json`: review-only bundle metadata.
- `run_artifacts/benchmark_plan.yml`: exact plan used for the run.
- `run_artifacts/results.json`: generated benchmark result.
- `run_artifacts/samples.csv`: per-request sample evidence.

## Recommendation JSON

The recommendation includes:

- `recommendation_status`
- `recommended_endpoint_id`
- `objective`
- `confidence`
- `placement_summary`
- `business_impact`
- `decision_table`
- `input_quality`
- `sensitivity_analysis`
- `reason_codes`
- `warnings`
- `caveats`

The decision table includes raw metrics and review fields such as primary strength, primary risk, cost delta, latency headroom, and why a candidate was or was not selected.

## Status Values

- `RECOMMENDED`: a passing endpoint was selected under the configured objective.
- `NO_CLEAR_WINNER_REVIEW_REQUIRED`: evidence supports review but not a clean selection.
- `NO_ENDPOINT_MEETS_CONSTRAINTS`: no endpoint passed the declared benchmark constraints.
- `INSUFFICIENT_DATA`: benchmark evidence is too thin for a credible recommendation.

Endpoint statuses:

- `PASS`
- `REVIEW`
- `FAIL`
- `INELIGIBLE`
- `ELIGIBLE_NOT_RUN`

## Markdown Report Shape

`recommendation.md` is ordered for human review:

1. Placement decision.
2. Why the endpoint won.
3. Business impact.
4. Tradeoff summary.
5. Sensitivity and decision stability.
6. Endpoint comparison.
7. Data-location result.
8. Reliability and token evidence.
9. Risk, blockers, warnings, and caveats.
10. Recommended human questions.
11. Raw benchmark appendix.

## Caveats

Outputs are review-only. They do not approve production deployment, guarantee performance, verify policy compliance, evaluate answer quality, reserve capacity, or authorize procurement.
