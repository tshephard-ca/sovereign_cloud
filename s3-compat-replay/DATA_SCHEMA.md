# Data Schema Overview

Primary versioned artifacts:

- `usage-profile.json`
- `probe-plan.yml`
- `probe-results.json`
- `mismatches.csv`
- `compat-summary.json`
- `case.yml`
- `redaction-report.json`
- `questionnaires/app-owner-questions.yml`
- `questionnaires/field-review-notes.yml`
- `real-world-assessment.json`

Real-world fixture support files are local evidence inputs, not source-account fetches:

- `sanitized-http-trace.jsonl`
- `server-access-log.jsonl`
- `policy-context.yml`
- `business-context.yml`
- `corpus-calibration.yml`

`probe-results.json` includes `result_source` so reports can distinguish live probe output from deterministic simulated semantic fixtures.

Generate JSON Schema for supported structured artifacts:

```bash
s3-compat-replay schema usage-profile --output schemas/usage-profile.schema.json
s3-compat-replay schema probe-plan --output schemas/probe-plan.schema.json
s3-compat-replay schema probe-results --output schemas/probe-results.schema.json
s3-compat-replay schema case --output schemas/case.schema.json
s3-compat-replay schema real-world-assessment --output schemas/real-world-assessment.schema.json
```

Validate an artifact:

```bash
s3-compat-replay validate out/usage-profile.json --type usage-profile --strict
```

CSV outputs keep stable column ordering because they are intended for review workflows and lightweight automation.
