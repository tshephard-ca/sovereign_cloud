# Data Contribution Guide

Do not contribute raw CloudTrail-style logs, raw source bucket configuration, endpoint URLs, credentials, customer names, provider names, or object keys.

The accepted contribution unit is a redacted compatibility case bundle created by:

```bash
s3-compat-replay bundle create \
  --profile out/usage-profile.json \
  --plan out/probe-plan.yml \
  --results out/probe-results.json \
  --mismatches out/mismatches.csv \
  --output case-bundle.zip \
  --shareable \
  --strict-redaction
```

Before sharing, validate it:

```bash
s3-compat-replay bundle validate \
  --bundle case-bundle.zip \
  --strict-redaction
```

Rules:

- Share redacted case bundles only.
- Keep raw evidence local.
- Share sanitized trace/access-log evidence only when it has been reduced to key shapes, header classes, status codes, and timing buckets.
- Use `questionnaires/field-review-notes.yml` for outcome feedback.
- Mark false positives and missed issues without naming customers, endpoints, or providers.
- Public fixtures must be synthetic or redacted beyond re-identification risk.
