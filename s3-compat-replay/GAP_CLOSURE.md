# Gap Closure Record

This file records the real-world data and output-coverage gaps closed by the deterministic fixture, analysis, probe-plan generation, simulated semantic results, and assessment loop.

The verification artifact from the latest local run is:

```text
out/gap-closure-final/run/assessment.json
```

Expected verification result:

```text
status: PASS
input_gaps: []
output_gaps: []
plan_family_coverage_percent: 100.0
```

## Input Gaps Closed

| Gap | Closure |
| --- | --- |
| `NO_SOURCE_HTTP_TRANSCRIPT` | `real-world generate` writes `sanitized-http-trace.jsonl` with redacted methods, key shapes, header classes, query-auth evidence, timing, and retry fields. |
| `NO_OBJECT_BODIES` | Request hints now include body classes and size buckets, preserving the no-source-body boundary while giving probe generation realistic synthetic body intent. |
| `NO_IAM_OR_BUCKET_POLICY_CONTEXT` | `policy-context.yml` captures offline authorization shapes and policy-owner review context without source account calls. |
| `NO_SERVER_ACCESS_LOG_CORRELATION` | `server-access-log.jsonl` provides sanitized request/result rows for header, status, timing, retry, and size-bucket coverage. |
| `NO_USER_IDENTITY_CONTEXT` | HTTP trace and policy context include redacted requester and identity-shape fields. |
| `NO_EXACT_HEADER_COVERAGE` | Sanitized HTTP/access-log fixtures preserve header classes and selected safe header values needed for probe planning. |
| `NO_LATENCY_OR_RETRY_DISTRIBUTION` | HTTP trace and access-log rows include informational timing and retry fields, without treating them as a benchmark. |
| `NO_REAL_CUSTOMER_DISTRIBUTION` | `corpus-calibration.yml` records representative frequency calibration separately from raw customer data. |
| `LIMITED_ERROR_SHAPE_VARIETY` | The generator emits forbidden, invalid range, precondition, invalid request, missing object, and access-denied style error shapes. |
| `NO_PAGINATION_TOKEN_DISTRIBUTION` | Request hints and generated list events include truncated listing and continuation-token shapes. |
| `NO_UNUSUAL_KEY_CHARACTER_SET` | Generated keys include encoded spaces and reserved URL characters while outputs use key-shape redaction. |
| `NO_PRESIGNED_EXPIRATION_DISTRIBUTION` | Request hints include presigned expiration buckets for short, common, and long-lived links. |
| `NO_EVENT_NOTIFICATION_CONTEXT` | Bucket config includes offline event-notification context for static review and report questions. |
| `NO_REPLICATION_CONTEXT` | Bucket config includes offline replication context for static review and report questions. |
| `NO_REQUESTER_PAYS_TRAFFIC` | Request hints and probe-plan generation now model requester-pays traffic and payer-header checks. |
| `NO_LARGE_MULTIPART_DISTRIBUTION` | Access-log rows and request hints include multipart size buckets without source object bodies. |
| `NO_BUCKET_POLICY_OR_OWNERSHIP_EDGE_CASES` | Bucket config and policy context include ownership-control and authorization edge-case shapes. |
| `MISSING_ENCRYPTION_HEADERS_EVIDENCE` | Generated events, hints, bucket config, and probe plan include encryption-header evidence and synthetic checks. |

## Output Gaps Closed

| Gap | Closure |
| --- | --- |
| `SIMULATED_RESULTS_NOT_LIVE_ENDPOINT` | Probe results now carry explicit `result_source` provenance. Simulated results validate reporting coverage; live endpoint certification still requires `probe` against a user-supplied scratch bucket. |
| `NO_CONDITIONAL_REQUEST_PROBES` | Probe plans include `conditional_requests` probes for conditional object reads. |
| `NO_RANGE_GET_PROBES` | Probe plans include `range_gets` probes for bounded partial reads. |
| `NO_ENCRYPTION_HEADER_PROBES` | Probe plans include `encryption_headers` probes for synthetic encryption-header behavior. |
| `NO_METADATA_HEADER_ROUNDTRIP_PROBES` | Probe plans include metadata header round-trip probes from request hints. |
| `NO_PRESIGNED_EXPIRY_BOUNDARY_PROBES` | Probe plans include presigned expiry boundary probes from expiration buckets. |
| `NO_CORS_MULTI_ORIGIN_MATRIX` | CORS probe generation expands hinted origins and methods within the probe limit. |
| `NO_LIST_PAGINATION_PROBES` | Probe plans include bounded continuation-token pagination checks. |
| `NO_DELETE_MARKER_DEEP_PROBES` | Versioning plans include delete-marker behavior checks where versioning evidence exists. |
| `LIFECYCLE_STATIC_ONLY` | Lifecycle remains non-mutating, but output now includes an explicit lifecycle validation plan instead of silently stopping at a single static note. |
| `NO_CONSISTENCY_MODEL_PROBES` | Probe plans include bounded read-after-write/list consistency checks with timing recorded as informational output. |
| `NO_POLICY_AUTHZ_DIFFERENTIATION` | Probe plans and reports include authorization-context review probes to separate likely policy questions from semantic failures. |
| `NO_OWNERSHIP_CONTROLS_PROBES` | Probe plans include ownership-control checks and associated mismatch codes. |
| `NO_REQUESTER_PAYS_PROBES` | Probe plans include requester-pays checks when hints require payer-header behavior. |
| `NO_TIMING_DISTRIBUTION` | Probe step results include `duration_ms` for informational timing distribution. |
| `NO_MULTI_REGION_OR_ADDRESSING_MATRIX` | Assessment accepts compatibility matrix artifacts and records multi-target/addressing comparison coverage. |
| `NO_APPLICATION_CONFIRMATION_REQUIRED_FIELDS` | Assessment accepts questionnaire artifacts and business context so app-owner confirmation fields are part of coverage. |
| `GENERIC_BUSINESS_IMPACT_FOR_UNKNOWN_CODES` | Mismatch codes produced by the generator now have explicit business-impact and app-owner question mappings. |

## Reproduction

Run the full deterministic loop from the repository root:

```bash
PYTHONPATH=src python -m s3_compat_replay.cli real-world generate --output-dir out/gap-closure-final/input --event-count 180
PYTHONPATH=src python -m s3_compat_replay.cli analyze --cloudtrail out/gap-closure-final/input/cloudtrail --source-bucket source-bucket-example --request-hints out/gap-closure-final/input/request-hints.yml --bucket-config out/gap-closure-final/input/source-bucket-config.yml --output-profile out/gap-closure-final/run/usage-profile.json --output-plan out/gap-closure-final/run/probe-plan.yml --output-needs out/gap-closure-final/run/compatibility-needs.csv --redact --top-events 1000 --max-probes 100
PYTHONPATH=src python -m s3_compat_replay.cli real-world simulate-results --plan out/gap-closure-final/run/probe-plan.yml --output-results out/gap-closure-final/run/probe-results.json --output-mismatches out/gap-closure-final/run/mismatches.csv
PYTHONPATH=src python -m s3_compat_replay.cli summarize --profile out/gap-closure-final/run/usage-profile.json --results out/gap-closure-final/run/probe-results.json --output-summary out/gap-closure-final/run/compat-summary.json --output-markdown out/gap-closure-final/run/compat-summary.md
PYTHONPATH=src python -m s3_compat_replay.cli questionnaire generate --profile out/gap-closure-final/run/usage-profile.json --mismatches out/gap-closure-final/run/mismatches.csv --output out/gap-closure-final/run/app-owner-questions.yml --output-markdown out/gap-closure-final/run/app-owner-questions.md
PYTHONPATH=src python -m s3_compat_replay.cli compare-results --profile out/gap-closure-final/run/usage-profile.json --results out/gap-closure-final/run/probe-results.json --output-matrix out/gap-closure-final/run/compat-matrix.json --output-markdown out/gap-closure-final/run/compat-matrix.md
PYTHONPATH=src python -m s3_compat_replay.cli real-world assess --cloudtrail out/gap-closure-final/input/cloudtrail --request-hints out/gap-closure-final/input/request-hints.yml --bucket-config out/gap-closure-final/input/source-bucket-config.yml --http-trace out/gap-closure-final/input/sanitized-http-trace.jsonl --server-access-log out/gap-closure-final/input/server-access-log.jsonl --policy-context out/gap-closure-final/input/policy-context.yml --business-context out/gap-closure-final/input/business-context.yml --corpus-calibration out/gap-closure-final/input/corpus-calibration.yml --profile out/gap-closure-final/run/usage-profile.json --plan out/gap-closure-final/run/probe-plan.yml --results out/gap-closure-final/run/probe-results.json --summary out/gap-closure-final/run/compat-summary.json --matrix out/gap-closure-final/run/compat-matrix.json --questionnaire out/gap-closure-final/run/app-owner-questions.yml --output-json out/gap-closure-final/run/assessment.json --output-markdown out/gap-closure-final/run/assessment.md
```

