# Demo: From Screen Trace To Review Package

This demo shows the core business workflow: turn recorded host-screen evidence into a review package before wrapper/API implementation.

## Run

```bash
host-screen-contracts generate-corpus \
  --output out/generated_corpus

host-screen-contracts review-package \
  --package out/generated_corpus/synthetic_order_inquiry_multi_case \
  --output-dir out/order_inquiry_review
```

## What To Show

Open these outputs:

- `out/order_inquiry_review/executive_summary.md`
- `out/order_inquiry_review/readiness.json`
- `out/order_inquiry_review/canonical_contract.yml`
- `out/order_inquiry_review/api_candidate.openapi.yml`
- `out/order_inquiry_review/drift_evidence.yml`
- `out/order_inquiry_review/privacy_report.json`

## Demo Narrative

1. The input is a local package of neutral JSONL traces and a field map.
2. Canonical success and error cases shape the API contract candidate.
3. Drift cases are kept as evidence and do not mutate the canonical API shape.
4. Replay evidence proves the generated contract is consistent with recorded traces.
5. Privacy findings show what must be sanitized before sharing.
6. Readiness status says whether the package is blocked, review-required, or ready for human review.

## Expected Result

For `synthetic_order_inquiry_multi_case`, the review package should be `review_required`, not blocked. It has strong business-review value but remains synthetic evidence, so the next step is an approved sanitized local trace package.

## Important Boundary

This demo does not connect to a live host, push a wrapper, execute credentials, or prove production readiness. It produces a review artifact for decision-making.
