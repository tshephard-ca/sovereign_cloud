# Architecture

The core pipeline is intentionally small:

1. Input bundle or explicit input files.
2. Validation and endpoint eligibility.
3. Benchmark plan generation.
4. HTTP or simulator benchmark execution.
5. Metric aggregation and benchmark status evaluation.
6. Recommendation and business-impact calculation.
7. Decision bundle rendering.

## Modules

- `bundles.py`: deterministic input bundle generation, bundle validation, rate-card overlay, and decision bundle writing.
- `prompt_packs.py`: synthetic prompt generation with business-task metadata.
- `workload_profile.py`: workload and prompt loading.
- `endpoint_profile.py`: endpoint candidate loading.
- `constraints.py`: policy, reliability, latency, throughput, and economics constraints.
- `validators.py`: endpoint eligibility checks before benchmarking.
- `plan.py`: benchmark plan construction.
- `http_client.py`: benchmark execution, local simulator use, response parsing, and economics attachment.
- `metrics.py`: aggregate latency, throughput, token, error, and timeout metrics.
- `scoring.py`: PASS, REVIEW, FAIL, INELIGIBLE, and ELIGIBLE_NOT_RUN classification.
- `recommendation.py`: endpoint selection, decision rows, sensitivity analysis, placement summary, and business impact.
- `report.py`: executive summary and decision-first Markdown report rendering.

## Offline Simulator

Generated bundles include simulator metadata for each endpoint. When `--no-network` is used, the runner uses those simulator settings instead of making external calls. This supports demos, CI, and repeatable negative-case coverage.

## Rate-Card Boundary

Generated bundles separate endpoint capability metadata from economics. `rate_cards.yml` is authoritative when a bundle is used. This keeps user-supplied commercial assumptions visible and editable without hiding them inside endpoint transport metadata.

## Non-Goals

The architecture deliberately excludes routing, deployment, endpoint discovery, provider SDKs, control-plane calls, credential storage, quality evaluation, capacity reservation, alerting, and automatic approval.
