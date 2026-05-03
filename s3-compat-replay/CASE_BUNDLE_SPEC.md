# Compatibility Case Bundle

A compatibility case bundle is a redacted evidence package.

Required files:

```text
case.yml
usage-profile.json
probe-plan.yml
redaction-report.json
```

Optional files:

```text
probe-results/target-001.json
mismatches/target-001.csv
compat-summary.json
compat-summary.md
compat-matrix.json
compat-matrix.md
cleanup-manifest.json
evidence/key-shapes.json
evidence/request-shapes.json
evidence/feature-evidence.json
questionnaires/app-owner-questions.yml
questionnaires/app-owner-questions.md
questionnaires/app-owner-answers.yml
questionnaires/field-review-notes.yml
```

`case.yml` contains safe metadata only: case ID, workload type, event-count bucket, observed families, evidence sources, redaction level, and placeholder business outcome fields.

Bundles can be directories or ZIP files. Corpus import stores ZIP files under `corpus/bundles/` and a manifest index under `corpus/index/`.
