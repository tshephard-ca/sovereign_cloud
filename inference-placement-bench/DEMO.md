# Demo

This demo shows the intended product flow: generate complete benchmark input data, run an offline deterministic preflight, and review a decision bundle.

## Standard Placement Review

```bash
inference-placement-bench init-bundle \
  --template low-latency-chat \
  --output /tmp/ipb-low-latency \
  --prompt-count 50

inference-placement-bench evaluate \
  --bundle /tmp/ipb-low-latency \
  --output-bundle /tmp/ipb-low-latency-out \
  --no-network \
  --now 2026-01-01T00:00:00Z
```

Open `/tmp/ipb-low-latency-out/executive_summary.md` first. It gives the decision, confidence, business impact, tradeoff, and human review focus before the raw benchmark tables.

Then open `/tmp/ipb-low-latency-out/recommendation.md` for the full review package. It starts with the placement decision and then shows endpoint comparison, data-location result, reliability evidence, caveats, and raw benchmark rows.

## Negative Scenario Coverage

The generator includes scenario templates that create useful failure and review cases:

```bash
for template in \
  location-blocked-fastest \
  cheapest-latency-risk \
  streaming-required-missing \
  high-timeout-review \
  no-passing-endpoints
do
  inference-placement-bench init-bundle \
    --template "$template" \
    --output "/tmp/ipb-$template" \
    --prompt-count 20

  inference-placement-bench evaluate \
    --bundle "/tmp/ipb-$template" \
    --output-bundle "/tmp/ipb-$template-out" \
    --no-network \
    --max-requests 3 \
    --warmup-requests 0 \
    --now 2026-01-01T00:00:00Z
done
```

These cases demonstrate business-relevant outcomes:

- Fastest endpoint blocked by declared location policy.
- Cheapest endpoint missing the latency target.
- Streaming required by the workload but missing on some endpoints.
- Timeout risk affecting placement confidence.
- No endpoint passing the declared constraints.

## What To Review

Review these files in order:

1. `executive_summary.md`: decision, tradeoff, business impact, human review focus.
2. `recommendation.md`: full decision table and evidence.
3. `recommendation.json`: structured output for automation or downstream review tools.
4. `run_artifacts/samples.csv`: per-request evidence for debugging.
5. `input_hashes.json`: input fingerprint for handoff integrity.

The demo is deterministic, local, and simulator-backed. Replace generated endpoint metadata, request templates, and rate cards before using the workflow against real endpoints you are authorized to benchmark.
