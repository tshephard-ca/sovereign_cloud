# Input Contract

The MVP consumes local YAML and JSONL only.

## Workload Profile

`workload.yml` describes one workload:

- `workload_id`
- workload type
- model expectations
- prompt file
- request count, warmups, concurrency, timeout
- generic HTTP request template
- response extractors

The workload profile should describe the shape of the workload, not a production routing policy.

## Endpoint Candidates

`endpoints.yml` declares candidate endpoint metadata:

- endpoint ID and display name
- base URL
- response mode
- auth source
- declared location
- capabilities
- request overrides
- optional simulator settings

Declared location is user-supplied metadata. The tool does not verify data residency.

## Constraints

`constraints.yml` contains review thresholds:

- allowed declared countries, regions, data zones, and operator control labels
- p95 latency target
- time-to-first-token target
- inter-token latency target
- throughput target
- error and timeout target
- economics preferences
- recommendation objective and weights

Constraints are workload-specific. They are not a universal endpoint scorecard.

## Rate Cards

`rate_cards.yml` contains user-supplied economics. For generated bundles, it is authoritative and overrides endpoint-file economics during planning:

```yaml
currency: CAD
rate_cards:
  - endpoint_id: candidate_fast
    input_per_1m_tokens: 1.40
    output_per_1m_tokens: 4.50
    per_1k_requests: 0.0
```

The tool does not fetch prices, infer discounts, include taxes, or generate procurement commitments.

## Prompts

Prompt files are JSONL. Each row requires `prompt`; `id`, token estimates, and metadata are optional.

Generated prompt rows include synthetic metadata such as:

- `business_task`
- `business_impact`
- `prompt_shape`
- `data_sensitivity`
- deterministic seed and row number

Do not benchmark sensitive, personal, regulated, confidential, credential-bearing, or proprietary prompt data unless you are authorized to do so.

## Bundle Templates

The generator includes both positive and negative cases:

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
