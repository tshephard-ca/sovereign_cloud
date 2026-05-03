# host-screen-contracts

## What the project does

`host-screen-contracts` turns recorded host-screen evidence into a review package for API or wrapper planning. It consumes neutral JSON Lines terminal traces plus a field map, then produces a canonical transaction contract, an OpenAPI 3.1 candidate, replay evidence, drift evidence, privacy findings, readiness scoring, and an executive summary.

The main workflow is:

```text
recorded trace package -> validate -> extract canonical contract -> verify replay/privacy/drift -> review package
```

The project is designed as a deterministic evidence layer before wrapper implementation. Its value is making transaction shape, field semantics, replayability, drift risk, privacy risk, and handoff readiness visible before teams commit implementation budget.

## What the project does not do

It does not connect to hosts, emulate terminals, automate sessions, rewrite application code, modernize RPG, generate server code, migrate applications, prove production readiness, store credentials, or perform network access.

It is not a terminal emulator, live automation tool, source-code analyzer, modernization platform, API server, migration tool, or AI system.

## Why this exists

Many organizations have stable high-value host screen transactions that are hard to discuss as APIs. Before building a wrapper, teams need evidence: screens, input fields, output fields, transitions, error paths, privacy findings, drift risk, and replay tests. This project makes recorded screen behavior understandable, reviewable, and testable without touching source code or connecting to a live host.

## Quickstart

```bash
python -m pip install -e ".[test]"

host-screen-contracts generate-corpus \
  --output out/generated_corpus

host-screen-contracts review-package \
  --package out/generated_corpus/synthetic_order_inquiry_multi_case \
  --output-dir out/order_inquiry_review
```

The review package writes:

- `canonical_contract.yml`: the contract candidate shaped only by canonical success/error cases.
- `api_candidate.openapi.yml`: OpenAPI with screen-origin metadata.
- `test_transaction_replay.py`: offline replay evidence for canonical cases.
- `drift_evidence.yml`: drift cases compared against the primary canonical success path.
- `flow_graph.yml`: recorded graph across every case in the package.
- `privacy_report.json`: aggregate privacy findings.
- `readiness.json`: decision-oriented review status, blockers, and next actions.
- `executive_summary.md`: concise business-facing summary.
- `review_package.zip`: handoff bundle.

Low-level commands are still available when you want explicit control:

```bash
host-screen-contracts validate-trace \
  --trace examples/order_lookup.trace.jsonl

host-screen-contracts extract \
  --trace examples/order_lookup.trace.jsonl \
  --field-map examples/order_lookup.fields.yml \
  --transaction-id order_lookup \
  --output-contract out/order_lookup.contract.yml \
  --output-openapi out/order_lookup.openapi.yml \
  --output-replay-test out/test_order_lookup_replay.py \
  --output-replay-case out/order_lookup.case.yml \
  --summary out/order_lookup.summary.json

host-screen-contracts replay \
  --trace examples/order_lookup.trace.jsonl \
  --contract out/order_lookup.contract.yml \
  --case out/order_lookup.case.yml
```

Useful optional flags include `--redact`, `--strict`, `--screen-size 24x80`, `--openapi-path /transactions/order-lookup`, and `--config examples/thresholds.yml`.

Additional real-world-data commands:

```bash
host-screen-contracts sanitize-trace \
  --trace examples/customer_update.trace.jsonl \
  --field-map examples/customer_update.fields.yml \
  --output out/customer_update.redacted.trace.jsonl \
  --report out/customer_update.privacy.json

host-screen-contracts label-sheet \
  --trace examples/order_lookup.trace.jsonl \
  --field-map examples/order_lookup.fields.yml \
  --output out/order_lookup.labels.yml

host-screen-contracts compare \
  --contract out/order_lookup.contract.yml \
  --trace examples/order_lookup.trace.jsonl \
  --field-map examples/order_lookup.fields.yml \
  --output out/order_lookup.drift.json

host-screen-contracts dataset init \
  --package datasets/order_lookup \
  --transaction-id order_lookup \
  --maturity-level L1

host-screen-contracts dataset validate \
  --package datasets/order_lookup

host-screen-contracts dataset benchmark \
  --package datasets/order_lookup \
  --output out/order_lookup.benchmark.json

host-screen-contracts extract-package \
  --package out/generated_corpus/synthetic_customer_update_sensitive \
  --output-dir out/order_lookup_package

host-screen-contracts coverage-report \
  --package-root out/generated_corpus \
  --output out/generated_corpus/coverage.json

host-screen-contracts realism-report \
  --package-root out/generated_corpus \
  --output out/generated_corpus/realism.json
```

## Trace format

The core input is JSON Lines. Each line is one event: `screen`, `action`, or `note`.

A `screen` event includes rows, columns, text, optional cursor position, and optional field metadata. Field coordinates are 1-based. A field id may be omitted; the tool generates ids like `f_04_32`.

An `action` event includes an AID such as `ENTER` or `F3` and the input values entered into fields. A minimal transaction usually looks like:

```text
screen -> action -> screen
```

The core accepts recorded traces only. It does not open a live host connection.

## Field map

Field maps matter because screen traces often reveal coordinates and values, but friendly field names may require human labels or source metadata. A field map lets reviewers supply names, roles, types, sensitivity, and endpoint paths so the generated API contract does not use poor coordinate-only names.

Field-map names, roles, and types override deterministic inference. Field names inferred from nearby labels are marked as inferred and are not authoritative.

## OpenAPI output

The generated OpenAPI 3.1 document is a contract candidate for review and wrapper implementation. It is not server code, not a live wrapper, and not a claim that the transaction is safe to expose externally.

The document includes trace metadata using extensions such as `x-screen-flow`, `x-screen-field`, `x-field-confidence`, `x-source-screen-hash`, `x-contract-confidence`, and `x-generated-by`.

`validate-openapi` runs the local structural validator. If an environment already has an OpenAPI validator installed, `--external-validator-command` can run that local command as an optional extra check.

## Replay tests

Replay tests validate the recorded trace against the generated contract. They do not prove that a live host will behave the same today. The replay driver is offline-only and walks through the trace file; it does not automate an emulator, use credentials, or connect anywhere.

`extract` writes a first-class replay case YAML. The generated pytest loads the replay case and contract, recomputes current trace screen hashes, applies each recorded action, and checks expected response values.

## Drift detection

`compare` checks a saved contract against a new trace. It classifies differences as compatible, review-required, or breaking changes.

Detected changes include:

- screen count changed
- labels changed
- layout changed
- field moved or resized
- replay path changed
- unknown screen encountered

This is intended for wrapper maintenance conversations. A drift report says what changed in the recorded screen contract; it does not explain why the host application changed.

`extract-package` also writes `transaction.drift-baseline.json`, a compact baseline containing screen hashes, layout hashes, transitions, replay cases, flow graph metadata, and the comparison policy used for future drift review.

## Real-world data packages

Real host screen traces are often sensitive, licensed, and customer-specific. The project therefore uses local data packages instead of requiring raw trace sharing.

Package layout:

```text
transaction_package/
  manifest.yml
  traces/
  field_maps/
  cases/
  expected/
  review/
  privacy/
  provenance/
```

Data maturity levels:

- `L0`: synthetic examples.
- `L1`: domain-realistic synthetic traces.
- `L2`: manually captured non-production traces that are sanitized before sharing.
- `L3`: real trace structure with fake or tokenized values.
- `L4`: real multi-case packages.
- `L5`: drift packages showing the same transaction across screen changes.
- `L6`: portfolio packages where only aggregate metrics may be shared.

Synthetic generated packages use `maturity_level: L1` or `L0` for actual evidence level and may set `simulates_maturity_level` to show the kind of real package shape they exercise. This avoids treating deterministic examples as customer-trace proof.

Manifest cases can declare purpose:

- `canonical_success`: shapes the API success contract.
- `canonical_error`: shapes recorded error response evidence.
- `drift_evidence`: compared against the canonical success path, but does not change the API contract.
- `navigation`: records setup/menu traversal without credentials.
- `non_contract`: useful for flow review, but not an API candidate.
- `guardrail`: intentionally weak or malformed behavior for validation hardening.
- `recorded_path`: backward-compatible default for older manifests.

Contribution modes:

- public sanitized package
- private validation package
- metric-only benchmark output

The safest default is to run capture, redaction, extraction, replay, drift comparison, and benchmarking locally, then share only sanitized packages or aggregate metrics.

`generate-corpus` creates a deterministic, synthetic, real-shaped package set for development and demonstrations. It is not customer data. Package names are explicit, for example `synthetic_order_inquiry_multi_case`, `synthetic_customer_update_sensitive`, and `synthetic_account_list_subfile`. The generated corpus covers inquiry, update, confirmation, not-found, validation-error, permission-denied, cancel, same-screen loop, volatile text, label drift, field movement, attribute drift, hidden fields, paired hidden-field absence, subfile/list selection with actual paging actions, navigation without credentials, boundary values, locale-formatted values, repeated labels, 27x132 screens, dates, leading-zero identifiers, long values, optional inputs, multiple request screens, plain-text-only traces, low-confidence traces, unsupported AID values, and sensitive-value redaction.

`coverage-report` verifies that the package root still covers those required scenarios. `realism-report` separates synthetic demonstration data from higher-maturity local packages and reports evidence level, business-impact score, field-map coverage, privacy state, blockers, portfolio candidate buckets, and recommended next data.

`extract-package` writes per-case replay cases and contracts plus canonical package artifacts. Canonical success/error cases shape `canonical_contract.yml` and `api_candidate.openapi.yml`; drift and non-contract cases are kept in `drift_evidence.yml` and `flow_graph.yml`. In non-strict mode it writes candidates even when blockers exist; `--strict` makes blockers fail the command.

`dataset benchmark` reports contract-ready rate, review-required count, field-map coverage, inferred names, generated coordinate names, and package-level blockers.

## Privacy and security

The core is local-only. It has no telemetry, no network calls, no credentials, no host login, and no emulator dependency.

Traces may contain sensitive data. Use `--redact` before sharing generated outputs. Redaction preserves structural metadata such as row, column, length, field id, field names, hashes, and reason codes.

Use `sanitize-trace` to produce a redacted trace and `privacy-report` to identify values that are sensitive by field-map flag, hidden-field marker, name pattern, or likely identifier-like raw screen text. Findings include severity counts, confirmed sensitive counts, potential identifier-pattern counts, hidden-field counts, and highest unredacted severity. `--fail-on-sensitive-unredacted` can be used in automation.

`sanitize-trace --tokenize` replaces sensitive values with deterministic tokens. Tokenization is useful when matching repeated values matters, but the raw value should not leave the local environment.

Subfile-like screens include `subfile_regions` metadata in generated contracts and `x-subfile-regions` in OpenAPI output. This metadata names row ranges, option columns, paging indicators, and review reasons. The core still does not generate list APIs or pagination wrappers.

Recorded error paths can produce an OpenAPI `422` schema with recorded error-message fields. This is still a contract candidate for review, not a complete host error model.

## Proprietary and licensing boundary

The core does not bundle, invoke, link, or redistribute terminal-emulator code. It consumes neutral JSONL traces.

Optional future adapters must respect their own licenses. GPL or proprietary adapters should be separate from the Apache-2.0 core. Users are responsible for having rights to capture and use their own traces.

Production traces should come from a licensed emulator, approved recorder, or customer-provided trace exporter.

The core includes an adapter protocol for future trace-producing packages, but no live adapter implementation. Adapter packages should remain separate so licenses, credentials, platform-specific behavior, and operational risk do not enter the core.

## Data honesty caveats

Field names inferred from labels are not authoritative. A trace captures one path, not all business logic. Hidden fields may not be visible. Subfiles and pagination require review. Screen replay is not source-code unit testing. OpenAPI generation does not expose or secure the host transaction.

Use careful language when reviewing outputs: contract candidate, field name inferred from nearby label, response field selected from final screen, replay test validates the recorded trace, human review required, and source-level modernization not performed.

## Handoff bundles

`review-package` creates the preferred handoff directory and `review_package.zip`. `bundle` remains available for assembling individual files manually. Bundle completeness grades artifact presence; readiness is reported in `readiness.json` and still does not certify production readiness.

## Schemas

Versioned schemas live in `schemas/`:

- `trace.schema.json`
- `field_map.schema.json`
- `contract.schema.json`
- `replay_case.schema.json`
- `dataset_manifest.schema.json`

The Python models are the enforcement layer in the MVP. The schemas document the interchange formats and give future adapters a stable target.

## Reason-code dictionary

Warnings:

- `FIELD_NAMES_INFERRED`: one or more names came from nearby labels.
- `PLAIN_TEXT_ONLY_TRACE`: a screen lacks field metadata.
- `SUBFILE_LIKE_REGION_DETECTED`: list-like or paged screen content may need review.
- `FUNCTION_KEY_ONLY_SCREEN`: a screen appears to contain only navigation text.
- `VOLATILE_REGION_NOT_DECLARED`: changing text may need a volatile-region map.
- `REPEATED_SCREEN_HASH`: two screens share the same stable screen hash.
- `HIDDEN_FIELDS_NOT_CAPTURED`: hidden fields may not be represented.
- `GENERATED_COORDINATE_NAMES`: one or more names were generated from coordinates.
- `OUTPUT_FIELD_SELECTION_REQUIRES_REVIEW`: output fields were selected without a complete field map.
- `ERROR_SCREEN_RECORDED`: the recorded path includes an error-like screen.
- `UNSUPPORTED_AID`: an unrecognized AID was preserved as a raw value.

Blockers:

- `NO_SCREEN_EVENTS`: the trace has no screen events.
- `NO_ACTION_EVENTS`: the trace has no action events.
- `NO_INPUT_FIELDS`: no request fields could be identified.
- `NO_FINAL_OUTPUT_FIELDS`: no response fields could be identified.
- `AMBIGUOUS_FIELD_COORDINATES`: field references could not be resolved.
- `TRACE_SEQUENCE_INVALID`: sequence order or action flow is invalid.
- `FIELD_MAP_INVALID`: field-map references are invalid.
- `MULTI_PATH_FLOW_NOT_SUPPORTED_IN_MVP`: the trace appears to require branching.
- `SCREEN_SIZE_INVALID`: screen sizes conflict with strict expectations.
- `FIELD_COORDINATES_OUT_OF_BOUNDS`: a field is outside screen bounds.
- `GENERATED_COORDINATE_NAMES_IN_STRICT_MODE`: strict mode rejected coordinate-only names.

## Expansion roadmap

1. Live adapter plugin interface

   Define a `ScreenDriver` protocol for future adapters:

   - `current_screen()`
   - `send_aid()`
   - `set_field()`
   - `wait_for_screen_change()`

   Keep all live adapters outside core.

2. DDS/source metadata importer

   Allow user-supplied display metadata to improve field names, types, usage, and hidden-field awareness. Do not require source access. Do not parse source in MVP.

3. Contract drift detection

   Implemented as `compare` for single traces and `transaction.drift-baseline.json` for package extraction. Future work should add richer compatibility policies across approved repeated captures.

4. Batch portfolio mode

   Implemented through `benchmark`, `coverage-report`, and `realism-report --package-root`, including portfolio candidate buckets. Future work should add cross-directory portfolio aggregation.

5. Handoff bundle

   Implemented as `bundle` and `bundle-score`. Future work should add redacted trace fingerprints and stronger provenance metadata.

6. Error-path contracts

   Support multiple recorded cases: happy path, invalid input, not found, and permission denied. Generate richer OpenAPI error responses.

7. Human labeling workflow

   Implemented as `label-sheet`. Future work should add merge-back helpers that turn accepted worksheet edits into field maps.

8. Postman or Bruno collection generation

   Generate API-review collections from the OpenAPI document. Still do not generate a server.

9. Wrapper skeleton, optional and separate

   A future separate package may generate a thin wrapper skeleton around `ScreenDriver`. Keep it separate from core because live automation, credentials, security, and platform-specific behavior are deployment-specific.

10. Test-data reset hooks

   Future replay against live systems may require test-data reset. Define hook interfaces only. Do not implement live reset in core.
