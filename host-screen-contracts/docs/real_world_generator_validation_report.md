# Real-World Generator Validation Report

Current validation date: 2026-05-03

This report covers the deterministic generated-data workflow for `host-screen-contracts`. The generated corpus is intentionally synthetic. It is useful for development, demos, regression coverage, and review-workflow design; it is not customer-trace proof.

## Validation Workflow

```bash
PYTHONPATH=src python -m host_screen_contracts.cli generate-corpus \
  --output /tmp/hsc-final-corpus \
  --seed 123

PYTHONPATH=src python -m host_screen_contracts.cli coverage-report \
  --package-root /tmp/hsc-final-corpus \
  --output /tmp/hsc-final-coverage.json

PYTHONPATH=src python -m host_screen_contracts.cli realism-report \
  --package-root /tmp/hsc-final-corpus \
  --output /tmp/hsc-final-realism.json

PYTHONPATH=src python -m host_screen_contracts.cli review-package \
  --package /tmp/hsc-final-corpus/synthetic_order_inquiry_multi_case \
  --output-dir /tmp/hsc-final-review/order_inquiry

python -m pytest -q -p no:cacheprovider
```

The review-package command is the preferred end-to-end demo. It writes the canonical contract, API candidate, replay test, drift evidence, privacy report, readiness assessment, executive summary, and handoff ZIP from one package.

## Current Result

- Generated packages: 9 synthetic packages.
- Required coverage tags: 40.
- Covered required tags: 40.
- Coverage: 100%.
- Package validation: generated packages are structurally valid except the intentional low-confidence guardrail package, which carries expected blockers.
- Review package status for `synthetic_order_inquiry_multi_case`: `review_required`.
- Expected review reasons: synthetic evidence, privacy review, extraction warnings, and drift evidence.
- OpenAPI candidate: local structural validation passes.
- Replay: generated replay tests walk recorded traces.

The expected status is `review_required`, not `ready_for_review`, because the package is synthetic and includes drift evidence. That is deliberate: the corpus demonstrates how a team should reason about a transaction before committing wrapper implementation effort.

## Input Data Assessment

The generated corpus covers:

- inquiry, update, selection, confirmation, not-found, validation-error, permission-denied, cancel, unsupported AID
- volatile screen text, label drift, field movement drift, attribute drift
- hidden fields and paired hidden-field absence
- subfile/list selection with actual paging actions
- navigation without credential capture
- boundary values, optional inputs, date fields, locale-formatted values, leading-zero identifiers, long values
- repeated labels, wide screens, multiple request screens, plain-text-only traces, low-confidence fallback
- sensitive-value redaction scenarios

Each generated package includes explicit evidence metadata:

- `evidence_kind`: `domain_realistic_synthetic` or `deterministic_synthetic`
- `actual_maturity_level`: the actual evidence level, usually `L1` or `L0`
- `simulates_maturity_level`: the real-world package shape being exercised, such as `L3` or `L4`
- `cases`: a case map with purpose, such as `canonical_success`, `canonical_error`, `drift_evidence`, `non_contract`, or `guardrail`

This prevents deterministic examples from being mistaken for real multi-case or real drift evidence.

## Output Data Assessment

The outputs are now separated by decision purpose:

- `canonical_contract.yml`: shaped only by canonical success/error cases.
- `api_candidate.openapi.yml`: generated from the canonical contract candidate.
- `case_contracts/`: per-case contracts for inspection.
- `cases/`: per-case replay cases.
- `drift_evidence.yml`: drift cases compared against the primary canonical success path.
- `flow_graph.yml`: all recorded paths, including canonical, non-contract, guardrail, and drift evidence.
- `privacy_report.json`: confirmed sensitive findings separated from potential identifier patterns.
- `readiness.json`: blockers, review items, readiness dimensions, and next actions.
- `executive_summary.md`: concise handoff language for technical and business reviewers.
- `review_package.zip`: a portable review bundle with the key artifacts.

Drift and non-contract cases no longer silently change the API candidate. They remain visible evidence for review.

## Business Impact Signals

The strongest generated package is `synthetic_order_inquiry_multi_case` because it shows a recognizable wrapper-planning conversation: a successful inquiry, alternate value stability, a not-found path, label drift, field movement drift, volatile text, leading-zero identifiers, and date output.

`synthetic_customer_update_sensitive` is the strongest operational workflow package because it exercises sensitive inputs, hidden fields, multiple request screens, confirmation, cancel behavior, and update status.

`synthetic_exception_paths` is a control package for review gates: validation error, permission denied, cancel, unsupported AID, wide-screen layout, same-screen loop, and attribute drift.

## Remaining Evidence Gaps

These are not coding defects; they are evidence gaps that only approved local capture can close.

1. The generated corpus is synthetic and should not be used as production proof.
2. Trace volume is small and scenario-focused, not statistically representative.
3. There are no repeated recordings across days, users, terminal profiles, or host configuration states.
4. Login and menu navigation avoid credentials and do not model real sign-on.
5. Subfile row semantics remain simplified.
6. Error-path variety does not yet include every business condition, such as stale data, duplicate records, warning-but-continue, or partial success.
7. Field maps are cleaner than many real field maps.
8. Multilingual, double-byte, and right-to-left screen text are not covered.
9. Display attributes are represented lightly.
10. Real privacy, legal, retention, and capture-approval provenance must come from the user’s environment.

The next high-impact data step is an approved sanitized local package for one valuable transaction, with at least one canonical success case, one canonical error case, one replay case, a reviewed field map, and redaction evidence.
