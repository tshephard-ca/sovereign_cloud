# Business Cases

`inference-placement-bench` is most useful before a team commits integration time, traffic migration effort, or commercial effort to an inference endpoint.

## Primary Question

Which candidate endpoint should be reviewed for this workload after considering declared policy constraints, latency, streaming behavior, throughput, reliability, and user-supplied unit economics?

## Personas

- Platform engineering: compare endpoint candidates before integration work.
- Product engineering: confirm whether a user-facing workload has a plausible latency candidate.
- Operations: identify timeout, error-rate, and declared-location blockers before traffic is moved.
- Finance or commercial review: compare endpoint economics from supplied rate cards without turning the tool into a pricing system.
- Governance review: confirm that declared endpoint metadata satisfies the workload's declared location constraints.

## High-Impact Scenarios

- The fastest endpoint is not allowed by declared location policy.
- The cheapest endpoint misses user-experience latency.
- A streaming workload is pointed at non-streaming endpoints.
- Unit economics are missing for some candidates, making cost comparison incomplete.
- Synthetic prompts reveal that a real prompt pack is needed before review.
- Error or timeout rates show an integration blocker before production work starts.

## Business Value

The value is not that the tool proves production readiness. The value is that it turns endpoint selection from a meeting opinion into a reviewable artifact:

- A ranked decision table.
- Measured endpoint evidence.
- Policy and capability blockers.
- Cost and latency tradeoffs.
- Human review questions.
- Input fingerprints for handoff.

## Guardrails

The output is review-only. It should not be used as routing approval, production signoff, capacity reservation, compliance proof, quality evaluation, procurement approval, or service commitment.
