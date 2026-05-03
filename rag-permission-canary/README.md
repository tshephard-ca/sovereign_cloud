# rag-permission-canary

`rag-permission-canary` is a local-first permission-regression harness for existing RAG, AI search, and document summarization endpoints.

It answers one narrow release question:

> For this synthetic permission fixture, did tested users retrieve allowed documents while forbidden evidence stayed out of answers, citations, snippets, metadata, and raw context?

The business value is release evidence. A team can run the same permission pack before launch or before connector, index, ACL-sync, prompt, model, or response-schema changes. If restricted evidence leaks, the tool produces a CI-friendly failure and a reviewable artifact showing the leak channel.

## What It Does

- Generates deterministic allowed and forbidden canary queries.
- Builds an expected user/document access matrix.
- Checks answer text, citation document IDs, citation titles, snippets, metadata, and raw retrieved context.
- Verifies both safety and utility: forbidden content must not leak, and allowed content must produce positive evidence.
- Emits JSON, CSV, Markdown, JUnit, fixture-quality, access-matrix, boundary-coverage, and handoff-bundle artifacts.
- Runs locally except for the configured endpoint call during `run`.

## What It Does Not Do

It does not build RAG, implement access control, sync permissions, create embeddings, inspect identity providers, mutate content systems, evaluate answer quality, create an index, upload documents, or certify compliance. It is not a RAG platform, vector database, AI search engine, permissions engine, identity provider, content-management system, model gateway, AI governance platform, LLM judge, or compliance certification tool.

## Quickstart: Local Demo

Run a generated safe endpoint simulation. This does not call a network service.

```bash
rag-permission-canary run-demo \
  --output-dir out/demo-safe \
  --mode safe \
  --users 4 \
  --documents 20 \
  --seed 7 \
  --force
```

Expected decision:

```text
aggregate_status = PASS
release_decision = ALLOW_NEXT_STAGE
```

Run the same generated fixture against a deliberately leaky local simulation:

```bash
rag-permission-canary run-demo \
  --output-dir out/demo-leaky \
  --mode leaky \
  --users 4 \
  --documents 20 \
  --seed 7 \
  --force
```

Expected decision:

```text
aggregate_status = FAIL
release_decision = BLOCK_RELEASE
```

The generated demo writes:

- `content_set.yml`
- `test_users.yml`
- `permissions.yml`
- `endpoint.yml`
- `thresholds.yml`
- `canary_pack.yml`
- `canary_queries.csv`
- `fixture_quality.json`
- `access_matrix.csv`
- `boundary_coverage.csv`
- `run_safe/results.json` or `run_leaky/results.json`
- `permission_regression_report.md`
- `junit.xml`

## Standard Workflow

Validate hand-authored inputs:

```bash
rag-permission-canary validate \
  --content examples/content_set.yml \
  --users examples/test_users.yml \
  --permissions examples/permissions.yml \
  --endpoint examples/endpoint.yml
```

Generate a canary pack:

```bash
rag-permission-canary generate \
  --content examples/content_set.yml \
  --users examples/test_users.yml \
  --permissions examples/permissions.yml \
  --output-pack out/canary_pack.yml \
  --output-queries out/canary_queries.csv
```

Assess fixture quality and write the access matrix:

```bash
rag-permission-canary assess-fixture \
  --content examples/demo_enterprise_boundary/content_set.yml \
  --users examples/demo_enterprise_boundary/test_users.yml \
  --permissions examples/demo_enterprise_boundary/permissions.yml \
  --endpoint examples/demo_enterprise_boundary/endpoint.yml \
  --config examples/demo_enterprise_boundary/thresholds.yml \
  --pack examples/demo_enterprise_boundary/canary_pack.yml \
  --output-quality-json out/fixture_quality.json \
  --output-quality-markdown out/fixture_quality.md \
  --output-access-matrix out/access_matrix.csv \
  --output-boundary-coverage out/boundary_coverage.csv
```

Run against an endpoint you are authorized to test:

```bash
rag-permission-canary run \
  --pack out/canary_pack.yml \
  --endpoint examples/endpoint.yml \
  --content examples/content_set.yml \
  --output-results out/results.json \
  --output-test-results out/test_results.csv
```

Generate report and CI output:

```bash
rag-permission-canary report \
  --results out/results.json \
  --output-report out/permission_regression_report.md \
  --output-junit out/junit.xml
```

Create a review bundle:

```bash
rag-permission-canary handoff-bundle \
  --output-zip out/permission_canary_handoff.zip \
  --pack out/canary_pack.yml \
  --queries out/canary_queries.csv \
  --results out/results.json \
  --test-results out/test_results.csv \
  --report out/permission_regression_report.md \
  --junit out/junit.xml \
  --fixture-quality out/fixture_quality.json \
  --access-matrix out/access_matrix.csv \
  --boundary-coverage out/boundary_coverage.csv \
  --endpoint examples/endpoint.yml
```

## Inputs

`content_set.yml` describes synthetic documents, collections, metadata, body text, and exact canary spans.

`test_users.yml` describes test users, groups, attributes, and credential environment-variable names.

`permissions.yml` describes the expected permission model for the fixture. The MVP supports group and user ACL behavior; attribute ACLs are parsed for visibility but are not evaluated as a full policy engine.

`endpoint.yml` describes how to call the endpoint and how to extract answer text, citations, snippets, metadata, and raw context.

`thresholds.yml` configures query counts, leakage checks, allowed-evidence checks, reporting, and optional business context.

Use synthetic canaries. Do not put production secrets, regulated data, or real confidential documents into fixtures unless you are authorized to handle and share those artifacts.

## Generated Input Data

The repository includes a stronger generated fixture under:

```text
examples/demo_enterprise_boundary/
```

It contains 20 synthetic documents across HR, finance, legal, engineering, and public collections; 4 test users; allow/deny rules; high-entropy canary markers; high-entropy metadata markers; a generated canary pack; fixture quality output; and access/boundary coverage CSVs.

Regenerate it with:

```bash
rag-permission-canary generate-demo-fixtures \
  --output-dir examples/demo_enterprise_boundary \
  --users 4 \
  --documents 20 \
  --seed 7 \
  --force
```

## Output Interpretation

`PASS` means the tested permission pack found no forbidden evidence and allowed queries produced expected evidence.

`FAIL` means forbidden evidence appeared in at least one tested surface.

`REVIEW` means the run did not produce enough evidence to make a release decision.

`INSUFFICIENT_DATA` means the run did not execute enough valid tests.

The result JSON includes a decision block:

```json
{
  "release_decision": "BLOCK_RELEASE",
  "business_risk": "Forbidden evidence appeared through tested response surfaces.",
  "confidence": "HIGH",
  "tested_boundaries": 20,
  "surfaces_tested": ["answer", "citations", "snippets", "metadata", "raw_context"],
  "recommended_owner": "retrieval_endpoint_owner"
}
```

Decision values:

- `ALLOW_NEXT_STAGE`: tested evidence supports moving to the next release stage.
- `BLOCK_RELEASE`: forbidden evidence leaked; do not ship until reviewed and fixed.
- `HUMAN_REVIEW_REQUIRED`: evidence is incomplete or ambiguous.
- `INSUFFICIENT_DATA`: the run cannot support a release decision.

## Architecture

The core pipeline is intentionally small:

1. Load fixtures: `content_set.py`, `users.py`, `permissions.py`, `endpoint_profile.py`.
2. Build expected access boundaries: `access_matrix.py`.
3. Assess fixture strength: `fixture_quality.py`.
4. Generate deterministic cases: `canary_generate.py`, `query_templates.py`.
5. Execute endpoint calls: `http_client.py`, or local demo transport in `demo_runner.py`.
6. Extract response surfaces: `response_extract.py`.
7. Detect exact forbidden evidence: `leakage_detect.py`.
8. Score results and release decision: `scoring.py`, `decision.py`.
9. Emit evidence: `report.py`, `junit.py`, `handoff.py`.

Core logic remains deterministic, vendor-neutral, and LLM-free.

## CI Usage

`report` writes JUnit XML. `FAIL` maps to a JUnit failure. `REVIEW` maps to skipped unless `--fail-on-review` is passed.

Exit codes:

- `validate`: 0 valid, 1 invalid
- `assess-fixture`: 0 valid, 1 invalid
- `generate`: 0 generated, 1 validation error, 2 insufficient strict coverage
- `run`: 0 PASS or REVIEW, 1 runtime/validation error, 2 FAIL, 3 REVIEW with `--fail-on-review`
- `report`: 0 generated, 1 invalid input

## Privacy And Security

- Local-first.
- No telemetry.
- No LLM judge.
- No external calls except the configured endpoint during `run`.
- No credential storage.
- Credentials are read from named environment variables only.
- Redacted answer excerpts by default.
- Raw answers and raw context are not included in reports by default.
- Handoff bundles are review artifacts, not compliance certificates.

## Reason Codes

Generation: `CONTENT_SET_VALID`, `USERS_VALID`, `PERMISSIONS_VALID`, `CANARY_PACK_GENERATED`, `ALLOWED_QUERY_GENERATED`, `FORBIDDEN_QUERY_GENERATED`, `INSUFFICIENT_CANARY_COVERAGE`, `NO_FORBIDDEN_DOCS_FOR_USER`, `NO_ALLOWED_DOCS_FOR_USER`, `CANARY_TEXT_UNIQUE`, `CANARY_TEXT_NOT_UNIQUE`, `FORBIDDEN_TOKEN_OMITTED_FROM_QUERY`, `EXACT_CANARY_CHECK_CONFIGURED`.

Execution: `TEST_USER_AUTH_PRESENT`, `TEST_USER_AUTH_MISSING`, `ENDPOINT_REQUEST_SENT`, `ENDPOINT_RESPONSE_RECEIVED`, `RESPONSE_EXTRACTED`, `RESPONSE_EXTRACTOR_MISSING_FIELD`, `ANSWER_TEXT_MISSING`, `CITATIONS_MISSING`, `RAW_CONTEXT_MISSING`, `HTTP_ERROR`, `HTTP_AUTH_FAILURE`, `REQUEST_TIMEOUT`, `DRY_RUN_ONLY`, `NO_NETWORK_MODE`.

Pass/fail: `ALLOWED_QUERY_EXECUTED`, `FORBIDDEN_QUERY_EXECUTED`, `ALLOWED_EVIDENCE_FOUND`, `ALLOWED_EVIDENCE_MISSING`, `FORBIDDEN_CANARY_NOT_FOUND`, `FORBIDDEN_DOC_ID_NOT_CITED`, `FORBIDDEN_TITLE_NOT_FOUND`, `FORBIDDEN_METADATA_NOT_FOUND`, `FORBIDDEN_CANARY_LEAKED`, `FORBIDDEN_DOC_ID_CITED`, `FORBIDDEN_TITLE_LEAKED`, `FORBIDDEN_METADATA_LEAKED`, `FORBIDDEN_SNIPPET_LEAKED`, `FORBIDDEN_RAW_CONTEXT_LEAKED`, `QUERY_CONTAINED_FORBIDDEN_TEXT`, `QUERY_ECHO_REMOVED_FROM_CHECK`, `PERMISSION_REGRESSION_PASS`, `PERMISSION_REGRESSION_FAIL`, `HUMAN_REVIEW_REQUIRED`, `INSUFFICIENT_EVIDENCE`.

Fixture quality: `RAW_CONTEXT_CHECK_CONFIGURED`, `CITATION_CHECK_CONFIGURED`, `METADATA_CHECK_CONFIGURED`, `METADATA_MARKER_NOT_UNIQUE`, `USER_WITHOUT_BOTH_ALLOWED_AND_FORBIDDEN_DOCS`, `SMALL_TEST_PACK`.

## Data Honesty Caveats

1. A canary pack tests only supplied users, documents, permissions, and queries.
2. Exact canary matching does not detect every paraphrased leak.
3. Absence of a canary leak does not prove the whole endpoint is protected.
4. Synthetic content may not match production retrieval behavior.
5. The endpoint must already be configured to use the intended identity context.
6. The tool does not verify identity-provider, connector, index, or model internals.
7. Missing response fields reduce confidence.
8. User-supplied permissions may not reflect real production permissions.
9. Query wording can affect retrieval behavior.
10. This is a regression test, not an access-control implementation.

## Roadmap

1. Permission drift mode for changed grants and denies.
2. Response drift mode for newly leaking or fixed results.
3. Prompt-template packs for direct lookup, summarization, comparison, metadata filtering, citation requests, and no-results checks.
4. Optional semantic leakage plugin interface; core remains exact, deterministic, and LLM-free.
5. Connector-specific fixture importers that export generic YAML.
6. Multi-tenant batch mode.
7. Policy packs for legal, HR, finance, healthcare, public-sector, engineering, and support knowledge bases.
