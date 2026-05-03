# Remaining Gap Closure

This file tracks the final gaps left after the generated-data audit. Each gap is written as an engineering requirement, followed by the implemented closure.

## Gap 1: Synthetic Corpus Is Not Customer Data

Requirement: the project must not pretend generated examples are real customer traces. It must measure evidence quality and state what local data is still needed.

Closure:

- Generated packages use explicit synthetic package names.
- Manifests distinguish `actual_maturity_level` from `simulates_maturity_level`.
- Manifests declare `evidence_kind`, such as `domain_realistic_synthetic`.
- `realism-report` separates synthetic demonstration data from higher-maturity local packages.
- `readiness.json` keeps synthetic evidence in review-required status.
- Raw data remains local, and generated examples avoid service-provider, customer, or proprietary names.

## Gap 2: OpenAPI Validation Was Too Shallow

Requirement: generated OpenAPI must be checked beyond version and `$ref` existence, without adding a server generator or network dependency.

Closure:

- `validate-openapi` checks required top-level fields, path shape, operation metadata, responses, request/response schemas, required properties, field metadata extensions, screen-flow metadata, and optional error schema references.
- Duplicate screen-field names are preserved as field variants instead of silently overwriting schema metadata.
- Validation remains local and deterministic.

## Gap 3: Multi-Case Extraction Lacked an Explicit Flow Model

Requirement: a package with multiple cases must produce an explicit recorded flow graph and separate canonical cases from drift and non-contract evidence.

Closure:

- `flow_graph.yml` records nodes, edges, cases, transition counts, case kinds, warnings, blockers, and start/end hashes.
- `canonical_contract.yml` is shaped by canonical success/error cases.
- `drift_evidence.yml` records drift cases compared with the primary canonical success path.
- Non-contract cases remain visible for flow review without changing the API candidate.

## Gap 4: Subfile/List Screens Needed Reviewable Metadata

Requirement: subfile-like screens must be more than a warning. Reviewers need coordinates and indicators explaining why row-selection logic requires review.

Closure:

- Subfile-region analysis records repeated row patterns, option columns, paging indicators, row ranges, and review-required reason text.
- Contract screens and OpenAPI extensions include this metadata.
- Core does not generate list APIs or pagination wrappers.

## Gap 5: Error Paths Used Only Generic OpenAPI Responses

Requirement: error-path traces should expose reviewable error metadata when recorded, while keeping MVP behavior simple.

Closure:

- Error-message fields are preserved in contracts.
- OpenAPI generation emits a structured `422` schema when recorded error-message fields or error-screen warnings exist.
- The schema remains a review candidate, not a complete host error taxonomy.

## Gap 6: Handoff Was Still Too Artifact-Oriented

Requirement: the project needs a clear business-facing throughline from generated input data to reviewable output package.

Closure:

- `review-package` is the preferred end-to-end command.
- `readiness.json` reports blockers, review items, dimensions, and next actions.
- `executive_summary.md` explains business use, evidence boundaries, artifact locations, and recommended next steps.
- `review_package.zip` gathers the key handoff artifacts.
- `docs/demo.md`, `docs/business-impact.md`, and `docs/evidence-model.md` define the recommended demo and review language.

## Verification Expectations

The closure is complete when:

- `pytest -q -p no:cacheprovider` passes.
- `generate-corpus` creates full required coverage.
- `realism-report` identifies the generated corpus as synthetic demonstration data.
- `review-package` writes `canonical_contract.yml`, `api_candidate.openapi.yml`, `drift_evidence.yml`, `privacy_report.json`, `readiness.json`, `executive_summary.md`, and `review_package.zip`.
- Subfile package contracts include `subfile_regions`.
- Error-path OpenAPI contains a `422` schema when an error field is present.
