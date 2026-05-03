# Evidence Model

The project separates evidence level from scenario shape.

## Maturity Levels

- `L0`: minimal synthetic or guardrail data.
- `L1`: domain-realistic synthetic traces.
- `L2`: approved sanitized non-production capture.
- `L3`: real trace structure with fake or tokenized values.
- `L4`: real multi-case package.
- `L5`: real drift package across screen changes.
- `L6`: portfolio metrics only.

Generated examples use `maturity_level: L1` or `L0` and may set `simulates_maturity_level` to show the kind of real-world shape covered. They are still synthetic.

## Evidence Kind

- `deterministic_synthetic`
- `domain_realistic_synthetic`
- `sanitized_local_capture`
- `real_structure_tokenized`
- `real_multi_case`
- `real_drift`
- `portfolio_metrics`

## Case Purpose

- `canonical_success`: can shape success request/response contract.
- `canonical_error`: can shape recorded error response evidence.
- `drift_evidence`: compared to the primary canonical success path; must not change the API candidate.
- `navigation`: setup or menu traversal without credentials.
- `non_contract`: useful flow evidence, not an API candidate.
- `guardrail`: weak or malformed case used to harden validation.
- `recorded_path`: compatibility default for older manifests.

## Output Rule

Canonical artifacts are intentionally conservative:

- `canonical_contract.yml` and `api_candidate.openapi.yml` are shaped by canonical success/error cases.
- `drift_evidence.yml` records drift cases separately.
- `flow_graph.yml` includes all recorded cases for review.
- `readiness.json` explains blockers and review items without claiming production readiness.
