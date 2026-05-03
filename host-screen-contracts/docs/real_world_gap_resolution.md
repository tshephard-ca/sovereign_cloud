# Real-World Data Gap Resolution

Run date: 2026-05-03

This file tracks implementation closure for the real-world-data gap list. The closures improve deterministic development coverage, review-package quality, and business handoff clarity. They do not claim customer-trace proof; generated packages remain synthetic unless a user supplies approved sanitized local traces.

## Closure Ledger

1. Malformed and adversarial package roots

   Closed by `generate-adversarial-corpus`, which emits invalid manifests, invalid JSONL, duplicate sequence traces, out-of-bounds fields, and invalid field maps. Dataset validation and benchmarking report blockers instead of crashing.

2. Actual subfile paging traces

   Closed by `synthetic_account_list_subfile/traces/paged_selection.trace.jsonl`, which records `PAGEDOWN` followed by row selection on a later page. The flow graph includes the paging transition.

3. Login/menu navigation without credentials

   Closed by `synthetic_navigation_no_credentials`, which records menu traversal without credential capture, host login automation, or network access.

4. Multi-value hash-stability variants

   Closed by `synthetic_order_inquiry_multi_case/traces/happy_path_alt_value.trace.jsonl`. Tests verify that the same logical screens keep stable hashes across different order values.

5. Boundary values

   Closed by `synthetic_boundary_locale_values`, covering blank optional input, max-length input, invalid date, negative amount, decimal amount, and leading-zero-style codes.

6. Locale date/number variants

   Closed by `synthetic_boundary_locale_values/traces/locale_variant.trace.jsonl`, which includes locale-formatted amount and date text while preserving fixed-width string semantics.

7. Paired hidden-field present/absent traces

   Closed by `synthetic_customer_update_sensitive`, which includes hidden-field-present and hidden-field-absent recordings of the same transaction path.

8. Repeated-label screens

   Closed by `synthetic_repeated_labels`, which records repeated `Status`, `Code`, and `Amount` labels and uses field-map names to disambiguate output fields.

9. Canonical package OpenAPI generation

   Closed by `extract-package`, which writes `api_candidate.openapi.yml` from `canonical_contract.yml`. Drift and non-contract cases are not allowed to reshape this API candidate.

10. Package replay pytest generation

   Closed by `extract-package`, which writes `test_transaction_replay.py` that replays recorded cases in the package against the package contract artifacts.

11. Handoff-bundle completeness score

   Closed by `bundle_score.py`, `bundle`, `bundle-score`, and the newer `review-package` workflow. Bundle manifests include a structural completeness score, blockers, and recommended missing artifacts; `review-package` adds readiness and executive summary outputs.

12. Portfolio realism reports

   Closed by `realism-report --package-root`, which emits portfolio candidate buckets for quick wins, review-required cases, low-confidence packages, missing field maps, subfiles, privacy review, drift-prone packages, navigation/setup, and boundary/locale coverage.

13. Privacy severity categories

   Closed by `privacy-report`, which emits per-finding severity, severity counts, unredacted severity counts, highest unredacted severity, confirmed sensitive counts, hidden-field counts, and potential identifier-pattern counts.

14. Optional external OpenAPI validator hook

   Closed by `validate-openapi --external-validator-command`. The hook is optional, local-process only, and runs after the built-in structural validator.

15. Generated drift-baseline and drift-evidence artifacts

   Closed by `extract-package`, which writes `transaction.drift-baseline.json` plus `drift_evidence.yml`. Drift evidence is compared to the primary canonical success path and stays separate from the canonical API candidate.

16. Review-package handoff

   Closed by `review-package`, which runs validation, benchmarking, package extraction, OpenAPI validation, privacy reporting, realism scoring, readiness assessment, executive summary generation, and ZIP bundle creation.

17. Synthetic evidence honesty

   Closed by manifest evidence metadata: `evidence_kind`, `actual_maturity_level`, `simulates_maturity_level`, and per-case `purpose`.

## Residual Limitation

The remaining business-evidence gap is not implementation coverage. It is evidence level: synthetic packages are useful for deterministic development, demos, regression tests, and review workflow design, but real-world proof still requires approved sanitized local traces from real capture workflows.
