# s3-compat-replay

## What The Project Does

`s3-compat-replay` is a local-first compatibility preflight for S3-compatible object-storage migrations. It mines observed S3 API usage from CloudTrail-style data events, creates a safe synthetic probe plan, runs that plan against a user-supplied target endpoint and scratch bucket, and turns semantic mismatches into a cutover decision brief.

The tool answers one question:

> Which observed object-storage behaviors must work before cutover, which target semantics failed, and who owns the next remediation decision?

## What The Project Does Not Do

It does not migrate data, copy objects, read source objects, rewrite applications, create buckets, benchmark performance, manage lifecycle policy, price storage, or prove full cutover readiness.

It also does not infer full application dependencies, build a transfer service, manage bucket policies, schedule replication, or write production object keys to the target.

## Why This Exists

Object-copy success does not prove application compatibility. Applications may rely on S3 semantics such as versioning, tags, ACLs, multipart upload, presigned URLs, CORS, Object Lock, metadata headers, status codes, and error shapes.

This project turns observed API patterns into small synthetic probes so teams can catch semantic incompatibilities before a cutover exercise depends on them.

## Quickstart

Analyze CloudTrail-style events and generate a usage profile, probe plan, compatibility-needs CSV, and capability ledger:

```bash
s3-compat-replay analyze \
  --cloudtrail examples/cloudtrail/ \
  --source-bucket source-bucket-example \
  --request-hints examples/request-hints.yml \
  --bucket-config examples/source-bucket-config.yml \
  --output-profile out/usage-profile.json \
  --output-plan out/probe-plan.yml \
  --output-needs out/compatibility-needs.csv \
  --output-capability-ledger out/capability-ledger.csv \
  --redact
```

Run the synthetic probe plan against a scratch bucket on a target S3-compatible endpoint:

```bash
s3-compat-replay probe \
  --plan out/probe-plan.yml \
  --endpoint-url https://target-object.example.invalid \
  --target-bucket compat-scratch-bucket \
  --region us-east-1 \
  --access-key-env TARGET_ACCESS_KEY_ID \
  --secret-key-env TARGET_SECRET_ACCESS_KEY \
  --session-token-env TARGET_SESSION_TOKEN \
  --scratch-prefix compat-replay/ \
  --allow-writes \
  --output-results out/probe-results.json \
  --output-mismatches out/mismatches.csv
```

Summarize the profile and probe results:

```bash
s3-compat-replay summarize \
  --profile out/usage-profile.json \
  --results out/probe-results.json \
  --plan out/probe-plan.yml \
  --business-context out/business-context.yml \
  --output-summary out/compat-summary.json \
  --output-markdown out/compat-summary.md \
  --output-cutover-brief out/cutover-brief.json \
  --output-cutover-brief-markdown out/cutover-brief.md \
  --output-remediation-queue out/remediation-queue.csv \
  --output-capability-ledger out/capability-ledger.csv
```

Or build the main preflight package in one command when probe results already exist:

```bash
s3-compat-replay preflight package \
  --cloudtrail examples/cloudtrail/ \
  --source-bucket source-bucket-example \
  --request-hints examples/request-hints.yml \
  --bucket-config examples/source-bucket-config.yml \
  --business-context out/business-context.yml \
  --results out/probe-results.json \
  --output-dir out/preflight \
  --redact
```

The first file to read is `cutover-brief.md`. It separates evidence coverage from target semantic status and gives a cutover recommendation: `BLOCK`, `REVIEW`, or `PROCEED_WITH_CAVEATS`.

## Real-World Data Loop

The project now has a safe way to use real-world evidence without collecting raw logs or secrets:

```text
real logs/config -> local redaction -> case bundle -> corpus -> policy and probe improvements
```

The shareable unit is a redacted compatibility case bundle, not raw event data. A bundle can include a usage profile, probe plan, target probe results, mismatch report, summary, cutover brief, capability ledger, key-shape evidence, app-owner questions, field-review notes, and a redaction report.

Generate a deterministic realistic local fixture with broad operation coverage:

```bash
s3-compat-replay lab generate \
  --output-dir out/real-world-input \
  --source-bucket source-bucket-example \
  --event-count 180
```

The generated input includes mixed CloudTrail-style JSON, JSONL, and gzip records, request hints, offline bucket config, sanitized HTTP-trace rows, server-access-log rows, policy context, corpus-calibration notes, and business-context notes. It is synthetic, but shaped to exercise object reads, writes, deletes, list operations, multipart upload, tagging, ACL, versioning, CORS, presigned URLs, Object Lock, lifecycle context, metadata, range reads, conditional requests, encryption indicators, requester-pays traffic, pagination, policy/ownership edge cases, and realistic error shapes.

Generate simulated target results for report and business-impact validation without a live endpoint:

```bash
s3-compat-replay lab simulate-results \
  --plan out/probe-plan.yml \
  --output-results out/probe-results.json \
  --output-mismatches out/mismatches.csv
```

Generate the app-owner questions and comparison matrix used by the full assessment:

```bash
s3-compat-replay questionnaire generate \
  --profile out/usage-profile.json \
  --mismatches out/mismatches.csv \
  --output out/app-owner-questions.yml \
  --output-markdown out/app-owner-questions.md

s3-compat-replay compare-results \
  --profile out/usage-profile.json \
  --results out/probe-results.json \
  --output-matrix out/compat-matrix.json \
  --output-markdown out/compat-matrix.md
```

Assess generated input and output coverage:

```bash
s3-compat-replay lab assess \
  --cloudtrail out/real-world-input/cloudtrail \
  --request-hints out/real-world-input/request-hints.yml \
  --bucket-config out/real-world-input/source-bucket-config.yml \
  --http-trace out/real-world-input/sanitized-http-trace.jsonl \
  --server-access-log out/real-world-input/server-access-log.jsonl \
  --policy-context out/real-world-input/policy-context.yml \
  --business-context out/real-world-input/business-context.yml \
  --corpus-calibration out/real-world-input/corpus-calibration.yml \
  --profile out/usage-profile.json \
  --plan out/probe-plan.yml \
  --results out/probe-results.json \
  --summary out/compat-summary.json \
  --matrix out/compat-matrix.json \
  --questionnaire out/app-owner-questions.yml \
  --output-json out/real-world-assessment.json \
  --output-markdown out/real-world-assessment.md
```

The assessment reports input coverage, output coverage, business-impact findings, and explicit gaps. When all generated artifacts above are supplied, the deterministic fixture is expected to close the known input/output coverage gaps. Simulated results validate the reporting pipeline; they do not replace running probes against a real scratch bucket.

Create and validate a bundle:

```bash
s3-compat-replay bundle create \
  --profile out/usage-profile.json \
  --plan out/probe-plan.yml \
  --results out/probe-results.json \
  --mismatches out/mismatches.csv \
  --output out/case-bundle.zip \
  --workload-type application_upload_bucket \
  --shareable \
  --strict-redaction

s3-compat-replay bundle validate \
  --bundle out/case-bundle.zip \
  --strict-redaction
```

Import bundles into a private local corpus and summarize recurring patterns:

```bash
s3-compat-replay corpus import \
  --bundle out/case-bundle.zip \
  --corpus-dir corpus/

s3-compat-replay corpus summarize \
  --corpus-dir corpus/ \
  --output corpus-summary.md \
  --output-json corpus-summary.json
```

Generate app-owner questions from observed features and mismatches:

```bash
s3-compat-replay questionnaire generate \
  --profile out/usage-profile.json \
  --mismatches out/mismatches.csv \
  --output out/app-owner-questions.yml \
  --output-markdown out/app-owner-questions.md
```

Compare multiple target result files without ranking vendors:

```bash
s3-compat-replay compare-results \
  --profile out/usage-profile.json \
  --results out/target-001-results.json \
  --results out/target-002-results.json \
  --output-matrix out/compat-matrix.json \
  --output-markdown out/compat-matrix.md
```

Validate artifacts and export schemas:

```bash
s3-compat-replay validate out/usage-profile.json --type usage-profile --strict
s3-compat-replay schema probe-plan --output schemas/probe-plan.schema.json
s3-compat-replay schema real-world-assessment --output schemas/real-world-assessment.schema.json
```

## Case Bundles And Corpus

Case bundles are the mechanism for bringing real-world data into the project safely. They contain redacted compatibility evidence and can be stored as ZIP files or directories.

Required bundle files:

- `case.yml`
- `usage-profile.json`
- `probe-plan.yml`
- `redaction-report.json`

Common optional files:

- `probe-results/target-001.json`
- `mismatches/target-001.csv`
- `compat-summary.json`
- `compat-summary.md`
- `evidence/key-shapes.json`
- `evidence/request-shapes.json`
- `evidence/feature-evidence.json`
- `questionnaires/app-owner-questions.yml`
- `questionnaires/field-review-notes.yml`

The corpus commands are local-only. They help a team understand recurring workload shapes, blocker codes, review codes, and warning patterns across many redacted cases. They do not upload data.

## Policy Packs

Policy packs are report presets and evidence checklists for workload types. Built-in packs include:

- `application-uploads`
- `public-assets`
- `backup-archive`
- `regulated-retention`
- `data-lake`

Evaluate a policy pack:

```bash
s3-compat-replay policy evaluate \
  --policy policy-packs/application-uploads.yml \
  --profile out/usage-profile.json \
  --results out/probe-results.json \
  --output out/policy-evaluation.json
```

Policy packs can define required operation families, required hints, severity overrides, evidence-quality expectations, and human questions. They are not pricing models and do not rank targets.

## CloudTrail Limitations

CloudTrail-style data events are useful evidence, but they are not a full HTTP transcript.

- Logs are not guaranteed ordered traces of application requests.
- Data events must have been enabled for the relevant bucket and time range.
- Request and response fields can be incomplete, omitted, or truncated.
- Object bodies are not available.
- HTTP headers are incomplete.
- Presigned URL behavior is often not provable from logs alone.
- CORS behavior usually needs synthetic HTTP OPTIONS probes.
- Lifecycle behavior cannot be fully validated by a short replay.

The tool emits warning codes for these limitations instead of hiding them.

## Request Hints

`request-hints.yml` lets users provide offline context that logs often cannot prove, such as presigned URL usage, browser CORS origins, metadata headers, conditional requests, range reads, expected error-shape comparisons, content types, and example object tags.

Features observed only in request hints are marked as `REQUEST_HINTS`. Features observed in both logs and hints can be represented as combined evidence in probe and mismatch output.

## Bucket Config

`source-bucket-config.yml` is optional offline context supplied by the user. It can describe versioning, lifecycle, CORS, Object Lock, ownership controls, and requester-pays behavior.

The MVP never connects to the source bucket to fetch configuration. Static config comparison is allowed; time-based lifecycle execution testing is not part of the MVP.

## Probe Safety

The default posture is conservative.

- `analyze` is offline-only.
- `probe` is read-only unless `--allow-writes` is passed.
- Delete probes require `--allow-deletes`.
- ACL probes require `--allow-acl-tests`.
- Multipart probes require `--allow-multipart`.
- Object Lock probes require `--allow-object-lock-tests`.
- Every write uses tiny synthetic objects under `--scratch-prefix`.
- The scratch prefix must be non-empty, relative, at least 8 characters, and end with `/`.
- Source object keys are converted to key-shape templates; production object names are not used as target keys.
- Cleanup is best effort by default. If cleanup fails, a `cleanup-manifest.json` is written beside probe results.
- The tool does not access the source bucket.

## Output Interpretation

The decision package separates three ideas that are easy to confuse:

- `evidence_coverage_status`: whether the observed logs, request hints, and config are strong enough to drive a preflight.
- `target_semantic_status`: whether the target probe results matched the required S3-style semantics.
- `cutover_recommendation`: the practical decision signal: `BLOCK`, `REVIEW`, or `PROCEED_WITH_CAVEATS`.

The compatibility summary keeps `compatibility_status` as the target semantic status:

- `PASS`: required synthetic compatibility probes passed, no blocker mismatches were found, and evidence quality is usable.
- `REVIEW`: evidence is incomplete, required probes were skipped for safety, or semantics such as lifecycle, Object Lock, ACL, CORS, or presigned URLs need human validation.
- `FAIL`: at least one observed required behavior appears unsupported or mismatched, basic operations failed, or probe safety could not be established.

None of these statuses prove that an application can be cut over safely. They describe the result of this local semantic preflight only. The cutover brief is the business-facing artifact because it groups blockers by business flow, owner role, evidence, and next action.

## Reason-Code And Mismatch-Code Dictionary

Warning codes:

- `CLOUDTRAIL_NOT_ORDERED_TRACE`: log events are not treated as an ordered request trace.
- `CLOUDTRAIL_HEADERS_INCOMPLETE`: full HTTP headers were not available.
- `CLOUDTRAIL_PARAMS_TRUNCATED`: request parameters were missing or likely incomplete.
- `CLOUDTRAIL_RESPONSE_ELEMENTS_MISSING`: response elements were missing.
- `SOURCE_BODY_NOT_AVAILABLE`: source object bodies are not present in logs.
- `PRESIGNED_USAGE_NOT_PROVEN`: presigned use was not explicitly proven.
- `CORS_REQUIRES_HTTP_PROBE`: CORS requires synthetic HTTP OPTIONS validation.
- `LIFECYCLE_STATIC_ONLY`: lifecycle is reviewed statically only.
- `OBJECT_LOCK_REQUIRES_BUCKET_SUPPORT`: Object Lock tests require a scratch bucket with support already enabled.
- `READ_ONLY_MODE_SKIPPED_WRITE_PROBES`: write-dependent probes were skipped.
- `DESTRUCTIVE_PROBES_SKIPPED`: delete-dependent probes were skipped.
- `ACL_PROBES_SKIPPED`: ACL probes were skipped.
- `MULTIPART_PROBES_SKIPPED`: multipart probes were skipped.
- `OBJECT_LOCK_PROBES_SKIPPED`: Object Lock probes were skipped.
- `TLS_VERIFICATION_DISABLED`: TLS verification was disabled for lab use.

Mismatch codes:

- `OPERATION_UNSUPPORTED`
- `STATUS_CODE_MISMATCH`
- `ERROR_CODE_MISMATCH`
- `CRITICAL_HEADER_MISSING`
- `CRITICAL_HEADER_VALUE_MISMATCH`
- `METADATA_ROUNDTRIP_FAILED`
- `TAGGING_ROUNDTRIP_FAILED`
- `ACL_UNSUPPORTED_OR_DISABLED`
- `VERSIONING_TARGET_NOT_ENABLED`
- `VERSION_ID_BEHAVIOR_MISMATCH`
- `DELETE_MARKER_BEHAVIOR_MISMATCH`
- `MULTIPART_CREATE_FAILED`
- `MULTIPART_UPLOAD_FAILED`
- `MULTIPART_COMPLETE_FAILED`
- `MULTIPART_ABORT_FAILED`
- `COPY_OBJECT_FAILED`
- `PRESIGNED_URL_FAILED`
- `PRESIGNED_URL_HEADER_MISMATCH`
- `CORS_PREFLIGHT_MISMATCH`
- `OBJECT_LOCK_UNSUPPORTED`
- `OBJECT_LOCK_RETENTION_MISMATCH`
- `OBJECT_LOCK_LEGAL_HOLD_MISMATCH`
- `LIFECYCLE_NOT_TESTED`
- `XML_RESPONSE_PARSE_FAILED`
- `RESPONSE_BODY_HASH_MISMATCH`
- `BASIC_WRITE_READ_FAILED`
- `SCRATCH_PREFIX_SAFETY_FAILED`
- `CLEANUP_FAILED`

## Privacy And Security

CloudTrail-style logs may contain sensitive object keys, account IDs, ARNs, IP addresses, user agents, and request parameters.

- The tool runs locally.
- `analyze` makes no network calls.
- `probe` contacts only the endpoint URL supplied by the user.
- There is no telemetry.
- There are no external service calls.
- There is no source bucket access.
- There is no data migration.
- There are no source object reads.
- There are no production object writes.
- Credentials are read from explicitly named environment variables only.
- Credentials are never written to output files.
- Presigned URLs are redacted in output.
- Use `--redact` before sharing usage profiles, probe plans, or reports outside a trusted team.
- Use `bundle validate --strict-redaction` before importing a bundle into a corpus or sharing it.
- Public examples and contributed cases must be synthetic or redacted beyond re-identification risk.

## Proprietary And Platform Boundary

- The repo does not bundle, invoke, or redistribute migration tools.
- The repo does not depend on a proprietary object-storage platform.
- Users supply their own logs, endpoint, credentials, and scratch bucket.
- Target-specific behavior should be represented as config or optional plugins.
- Future provider-specific adapters must be optional and clearly licensed.

## Data Honesty Caveats

- CloudTrail-style logs are not a full HTTP transcript.
- Synthetic probes are not production traffic.
- Lifecycle is not time-tested in the MVP.
- Performance is not benchmarked.
- Source object data is not copied or validated.
- Exact provider error messages may differ without breaking application behavior.
- A successful probe plan does not prove full migration readiness.

## Expansion Roadmap

1. Batch bucket portfolio mode

   Analyze many buckets and summarize buckets with only basic GET/PUT usage, versioning dependencies, ACL dependencies, presigned URL risk, CORS/browser risk, Object Lock requirements, and buckets needing human review before cutover. This is useful for pre-sales scoping and migration prioritization.

2. Offline config importers

   Accept user-provided exported bucket configuration JSON for versioning, lifecycle, CORS, Object Lock, ownership controls, replication, and encryption. Do not connect to source accounts in core.

3. Provider-neutral compatibility matrix

   Let users run the same probe plan against multiple target endpoints and compare pass rate, blocker count, review count, feature gaps, and remediation questions. Do not rank vendors automatically.

4. Portfolio-level decision package

   Extend the cutover brief across many buckets so program managers can see which buckets are blocked, which are review-only, and which can proceed with caveats.

5. Questionnaire answer validation

   Validate app-owner answers and require explicit owner acknowledgement for blocker questions before a cutover package can move from `BLOCK` to `REVIEW`.

6. Live HTTP capture adapter

   Optional separate adapter that consumes sanitized HTTP traces from a customer-approved proxy. Keep it separate from core because HTTP captures may contain secrets, headers, and payload metadata.

7. Server access log correlation

   Support user-supplied server access logs to improve header/status coverage. Keep CloudTrail-style data events as the MVP input.

8. Application SDK fingerprinting

   Use userAgent and request shapes to identify SDK families and risky behaviors. Do not infer business criticality.

9. Lifecycle simulation planner

   Given lifecycle config, generate test cases and a human validation plan. Do not wait days or mutate production data.

10. Synthetic load-free performance hints

    Record response timings from probes as informational only. Do not call it a benchmark.

11. Policy pack library expansion

    Expand built-in policy packs and add organization-specific presets. These are labels, report templates, required-feature presets, and severity rules, not pricing models.
