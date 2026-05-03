# inference-placement-bench

`inference-placement-bench` is a local-first, review-only preflight for one inference workload. It compares candidate HTTP inference endpoints against declared workload needs, endpoint metadata, benchmark evidence, policy constraints, reliability thresholds, and user-supplied unit economics.

The narrow business question is:

> Which endpoint is the best review-only placement candidate for this workload, and what tradeoffs or blockers should humans review before integration work proceeds?

It produces a decision bundle rather than a production routing action.

## What It Does

- Builds a benchmark plan from a workload profile, endpoint candidates, constraints, prompts, thresholds, and rate cards.
- Runs generic HTTP JSON/SSE benchmarks or the built-in deterministic local simulator.
- Measures p95/p99 latency, time to first token, inter-token latency, throughput, error rate, timeout rate, and token usage.
- Applies declared data-location, streaming, context-window, reliability, latency, throughput, and economics constraints.
- Generates recommendation JSON, a decision-first Markdown report, an executive summary, samples CSV, results JSON, and input hashes.

## What It Does Not Do

It does not route production traffic, reserve capacity, deploy models, evaluate answer quality, fetch prices, verify compliance, manage control planes, store credentials, mutate endpoints, create infrastructure, or approve production placement.

## Quickstart

Install locally:

```bash
python -m pip install -e .
```

Generate a complete synthetic input bundle and run it offline:

```bash
inference-placement-bench init-bundle \
  --template low-latency-chat \
  --output benchmark_inputs/chat \
  --prompt-count 100

inference-placement-bench evaluate \
  --bundle benchmark_inputs/chat \
  --output-bundle out/decision_bundle \
  --no-network \
  --now 2026-01-01T00:00:00Z
```

The output bundle contains:

- `executive_summary.md`
- `recommendation.md`
- `recommendation.json`
- `results.json`
- `input_hashes.json`
- `bundle_manifest.json`
- `run_artifacts/benchmark_plan.yml`
- `run_artifacts/results.json`
- `run_artifacts/samples.csv`

## Generated Input Bundles

`init-bundle` creates all required input data:

- `workload.yml`
- `endpoints.yml`
- `constraints.yml`
- `thresholds.yml`
- `rate_cards.yml`
- `data_inventory.yml`
- `prompts/prompts.jsonl`
- `request_templates/*.yml`
- `runbook.md`

`rate_cards.yml` is authoritative for generated bundle economics. The endpoint file carries simulator and capability metadata; the rate-card file carries user-supplied comparison economics.

Useful templates:

- `low-latency-chat`
- `interactive-support-chat`
- `agent-tool-summary`
- `batch-document-summary`
- `cost-sensitive-embedding`
- `classification-triage`
- `location-blocked-fastest`
- `cheapest-latency-risk`
- `streaming-required-missing`
- `high-timeout-review`
- `no-passing-endpoints`

## Manual Workflow

Use the staged commands when you want to inspect or edit each artifact:

```bash
inference-placement-bench plan \
  --workload examples/workloads/chat_support.yml \
  --endpoints examples/endpoints.yml \
  --constraints examples/constraints.yml \
  --output-plan out/benchmark_plan.yml

inference-placement-bench run \
  --plan out/benchmark_plan.yml \
  --output-results out/results.json \
  --output-samples out/samples.csv

inference-placement-bench recommend \
  --results out/results.json \
  --constraints examples/constraints.yml \
  --output-recommendation out/recommendation.json \
  --output-report out/recommendation.md
```

Use `--dry-run` to build evidence without running requests. Use `--no-network` with generated bundles to force the local simulator path.

## Output Interpretation

- `RECOMMENDED`: one passing endpoint is the review-only placement candidate under the configured objective.
- `NO_CLEAR_WINNER_REVIEW_REQUIRED`: multiple candidates are close or evidence is incomplete.
- `NO_ENDPOINT_MEETS_CONSTRAINTS`: no measured candidate passed the declared constraints.
- `INSUFFICIENT_DATA`: the run did not produce enough credible benchmark evidence.

Endpoint benchmark statuses are `PASS`, `REVIEW`, `FAIL`, `INELIGIBLE`, and `ELIGIBLE_NOT_RUN`. None of these mean production approval.

## Documentation

- [Demo](DEMO.md)
- [Business Cases](docs/business_cases.md)
- [Architecture](docs/architecture.md)
- [Input Contract](docs/input_contract.md)
- [Output Contract](docs/output_contract.md)

## Privacy And Security

The tool is local-first. It has no telemetry, no credential storage, no endpoint discovery, no provider SDKs, and no control-plane integrations. Credentials are read only from explicitly named environment variables when a real endpoint profile requests them. Generated prompts are synthetic and generic, but user-supplied prompt files may contain sensitive data. Use `--redact` before sharing outputs.

## Data Honesty

A micro-benchmark is not a production load test, capacity certification, compliance proof, answer-quality evaluation, or procurement decision. Declared location metadata is not independently verified. Unit economics come from user-supplied rate cards. Synthetic prompts may not match production prompt length, cache behavior, concurrency, or content.

## Development

```bash
python -m pytest -q
```

Core tests run offline and do not require real endpoints.
