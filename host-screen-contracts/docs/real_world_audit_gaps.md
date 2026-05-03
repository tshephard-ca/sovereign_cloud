# Real-World Data Audit Gaps

This file is the historical gap ledger for the generated-data workflow. The original audit found that the project had useful trace parsing primitives but did not yet present a clean end-to-end business artifact.

## Original Findings

The initial generated corpus work exposed these gaps:

1. No deterministic corpus generator.
2. Sanitization gaps for sensitive values in raw screen text.
3. Hidden-field handling needed safer privacy reporting.
4. Privacy findings needed to respect explicit `sensitive: false`.
5. Plain-text-only traces lost mapped response values.
6. Multi-case field maps needed case scoping.
7. Benchmark scoring overstated readiness.
8. Package extraction lacked a clean canonical package artifact.
9. Replay case naming was misleading.
10. Drift compare could not distinguish alternate cases from drift evidence.
11. Dataset validation was too shallow.
12. OpenAPI output lacked local structural validation.

## Closure Status

All original gaps now have MVP implementations:

- `generate-corpus` creates deterministic synthetic packages with explicit provenance.
- `coverage-report` verifies required scenario coverage.
- `sanitize-trace` redacts sensitive mapped values, hidden fields, and likely sensitive raw screen text.
- `privacy-report` separates confirmed sensitive findings from potential identifier patterns.
- Plain-text-only traces can extract mapped values from fixed coordinates.
- Field-map entries support optional fields and case-scoped metadata.
- Replay cases include `case_id` and `case_kind`.
- `extract-package` writes per-case contracts, per-case replay cases, `canonical_contract.yml`, `api_candidate.openapi.yml`, `flow_graph.yml`, `drift_evidence.yml`, and legacy compatibility artifacts.
- `dataset validate` checks schemas, extraction, replay, privacy, and maturity expectations.
- `dataset benchmark` surfaces warnings, blockers, and readiness reductions.
- `validate-openapi` performs deterministic local structural validation.
- `review-package` produces the preferred handoff directory and ZIP bundle.

## Current Generated Corpus

The main corpus packages are:

- `synthetic_order_inquiry_multi_case`: happy path, alternate value, not-found path, label drift, and field movement drift.
- `synthetic_customer_update_sensitive`: sensitive update, hidden-field present/absent evidence, confirmation, and cancel.
- `synthetic_account_list_subfile`: subfile/list selection with paging.
- `synthetic_inventory_plain_text`: plain-text-only trace with field-map coordinates.
- `synthetic_navigation_no_credentials`: menu traversal without credential capture.
- `synthetic_boundary_locale_values`: boundary, optional, date, amount, and locale-formatted values.
- `synthetic_repeated_labels`: repeated screen labels disambiguated by field map.
- `synthetic_exception_paths`: validation error, permission denied, cancel, unsupported AID, wide screen, and attribute drift.
- `synthetic_low_confidence_guardrail`: intentional low-confidence fallback package.

## Remaining Non-Code Evidence Gaps

The remaining gaps are evidence quality issues, not missing MVP implementation:

- The corpus is synthetic.
- Real packages need approved capture, retention, and redaction provenance.
- Real host behavior needs repeated recordings over time.
- Field maps from real teams will be messier than generated field maps.
- Real business value needs at least one high-value local transaction package and review with application, QA, security, and operations stakeholders.
