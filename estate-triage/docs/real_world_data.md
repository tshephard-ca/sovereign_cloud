# Real-World Data Intake

The preferred real-world workflow is an Estate Evidence Bundle. A bundle keeps raw exports, mappings, policy, validation output, fingerprints, redacted assessment output, and workflow handoff artifacts together in one reproducible local directory.

## Bundle Shape

```text
estate-bundle/
  manifest.yml
  inputs/
    inventory.csv
    backup_export.csv
    utilization.csv
  mappings/
    inventory-map.yml
    backup-map.yml
    utilization-map.yml
  policies/
    thresholds.yml
  feedback/
    feedback.yml
  outputs/
    top.csv
    summary.json
    assessment.json
    validation.json
    input-fingerprints.json
    workflow/
      executive-summary.md
      business-worklist.csv
      data-request-checklist.csv
      evidence-packets.json
```

Raw inputs stay local. Outputs can be redacted with `minimal`, `standard`, or `strict` privacy profiles.

For stakeholder review, start with `outputs/workflow/`. The top-level `top.csv` and `assessment.json` are technical artifacts.

## Synthetic Bundle Generation

Generate a broad synthetic real-world-like bundle for coverage testing:

```bash
estate-triage generate-real-world-data \
  --output /tmp/estate-generated-bundle \
  --profile coverage \
  --overwrite
```

Generate a split-source bundle to exercise multiple inventory and backup exports:

```bash
estate-triage generate-real-world-data \
  --output /tmp/estate-generated-multi-source \
  --multi-source \
  --overwrite
```

Multi-source bundles include `source-metadata.yml` with source-window metadata. The secondary inventory file intentionally models a stale capture window, and the secondary backup file models a different backup export window. Bundle analysis turns those conditions into `STALE_SOURCE_WINDOW` and `SOURCE_WINDOW_SKEW` readiness findings.

Generate messy input fixtures for adapter and readiness validation:

```bash
estate-triage generate-real-world-data \
  --output /tmp/estate-generated-edge-cases \
  --edge-cases \
  --overwrite
```

The generated `edge-cases/` directory includes:

- duplicate inventory headers
- embedded commas and newlines inside quoted fields
- mixed MiB/GiB/TiB storage units and decimal-comma numeric values
- localized inventory and backup headers
- localized power-state values
- irregular line endings
- rows with extra and missing CSV columns
- malformed quoting that must fail clearly
- non-UTF-8 input that must fail clearly

These files are synthetic fixtures. They are intended to prove parser behavior and readiness reporting, not to represent statistical export frequency.

## Manifest

```yaml
bundle_version: 1.0.0
assessment_id: local-assessment-001
inputs:
  - path: inputs/inventory.csv
    kind: inventory
    mapping: mappings/inventory-map.yml
  - path: inputs/backup_export.csv
    kind: backup
    mapping: mappings/backup-map.yml
  - path: inputs/utilization.csv
    kind: utilization
    mapping: mappings/utilization-map.yml
policy:
  thresholds: policies/thresholds.yml
privacy:
  redaction_mode: strict
  hash_salt_file: .local-salt
outputs:
  directory: outputs
feedback: feedback/feedback.yml
```

## Mapping Workflow

Create a starter mapping:

```bash
estate-triage init-mapping \
  --kind inventory \
  --input raw_inventory.csv \
  --output mappings/inventory-map.yml
```

Validate with the mapping:

```bash
estate-triage validate \
  --kind inventory \
  --input raw_inventory.csv \
  --mapping mappings/inventory-map.yml \
  --output-json outputs/inventory-validation.json
```

The validation report includes warnings, data-quality findings, unmapped columns, recommended fields that are missing, matchability forecast, business-severity counts, prioritized data-request checklist items, and mapped-field profiles with sample values, blank percentages, unit/date-format detection, cardinality warnings, and mapping confidence.

Mapping files can include approval metadata:

```yaml
approved_by: local-reviewer
approved_at_utc: 2026-04-30T00:00:00Z
approval_notes: Reviewed against source export headers.
```

Validation reports preserve this approval record and also suggest conservative mapping alternatives for unmapped required or recommended fields. Suggested alternatives are not applied automatically.

## Identity Overrides

Known renames or reviewed source mismatches can be handled without editing raw CSVs:

```yaml
overrides:
  - inventory_uuid: uuid-current
    backup_name: previous-workload-name
    reason: Reviewed rename from local assessment notes.
    approved_by: local-reviewer
    approved_at_utc: 2026-04-30T00:00:00Z
```

Use the file during direct analysis:

```bash
estate-triage analyze \
  --inventory inputs/inventory.csv \
  --backup inputs/backup_export.csv \
  --identity-overrides mappings/identity-overrides.yml \
  --output outputs/top.csv
```

Bundles can set `identity_overrides: mappings/identity-overrides.yml` in `manifest.yml`. Applied overrides are recorded as `IDENTITY_OVERRIDE_APPLIED` data-quality findings.

Export an identity graph for downstream review:

```bash
estate-triage identity-graph \
  --inventory inputs/inventory.csv \
  --backup inputs/backup_export.csv \
  --identity-overrides mappings/identity-overrides.yml \
  --output outputs/identity-graph.json
```

The graph includes inventory and backup nodes, match edges, identity strategies, statuses, and decomposed confidence factors.

## Utilization Input

Utilization is optional but improves right-sizing confidence. Recommended columns:

```text
VM
VM UUID
sample_start_utc
sample_end_utc
cpu_avg_pct
cpu_p95_pct
cpu_max_pct
memory_avg_pct
memory_p95_pct
memory_max_pct
sample_count
```

The engine uses p95 utilization when inventory utilization is absent. If no utilization exists, right-sizing remains allocation-only and confidence is lower.

## Analyze A Bundle

```bash
estate-triage analyze-bundle examples/estate-bundle --top-n 25
```

Bundle analysis writes:

- ranked CSV
- structured assessment JSON
- summary JSON
- validation JSON
- input fingerprints

## Privacy Profiles

`minimal` redacts workload names and UUIDs.

`standard` also redacts common operational identifiers such as host, cluster, datacenter, tags, notes, backup job, backup policy, and repository.

`strict` additionally redacts source paths and string raw values in evidence traces while preserving row numbers, column names, numeric metrics, reason codes, and scores.

## Fingerprints

Fingerprints prove which local inputs were assessed without embedding raw files in output:

```bash
estate-triage fingerprint inputs/inventory.csv inputs/backup_export.csv \
  --output outputs/input-fingerprints.json
```

Each fingerprint includes file SHA-256, row count, columns, and a column hash.

## Feedback

Create a local feedback file:

```bash
estate-triage feedback-template \
  --assessment-id local-assessment-001 \
  --output feedback/feedback.yml
```

Feedback is local-only. It is intended for manual policy tuning, not automatic model training.

Supported feedback outcomes:

- `accepted`: finding became a real next-step discussion or work item.
- `rejected`: reviewer decided the finding should not proceed.
- `needs_more_data`: reviewer could not decide without more evidence.
- `duplicate`: finding duplicates another known item.
- `wrong_motion`: finding is useful, but assigned to the wrong primary motion.
- `false_positive`: finding is not valid for the stated motion.
- `wrong_match`: identity resolution matched the wrong workload.
- `already_known`: finding was already known before the assessment.
- `useful` and `not_useful`: legacy labels retained for backward compatibility.

Optional timing fields support local time-saved measurement:

```yaml
manual_triage_minutes: 120
tool_triage_minutes: 45
```

Feedback items can also record conversion:

```yaml
converted: true
next_step: deeper_assessment
```

Summarize feedback metrics:

```bash
estate-triage feedback-summary --feedback feedback/feedback.yml
```

The summary includes accepted/rejected rates, false-positive rate, missed-opportunity count, conversion rate, next-step counts, and time-saved metrics when timing fields are present.

Aggregate multiple reviewed assessments into a local outcome ledger:

```bash
estate-triage outcome-ledger feedback/run-001.yml feedback/run-002.yml
```

Compare repeated assessment outputs:

```bash
estate-triage compare-assessments \
  --baseline outputs/assessment-before.json \
  --current outputs/assessment-after.json
```

Compare a candidate policy against an existing assessment before adopting it:

```bash
estate-triage policy-impact \
  --assessment-json outputs/assessment.json \
  --candidate-policy policies/candidate-policy.yml
```

The report counts score changes, primary-motion changes, and per-workload deltas.

Generate local workflow handoff artifacts from an assessment:

```bash
estate-triage workflow-pack \
  --assessment-json outputs/assessment.json \
  --output-dir outputs/workflow
```

The workflow pack writes per-motion queues, evidence packets, ranking-mode comparison, task CSV, discovery plan, and executive summary Markdown. It stays local and does not create tickets or call external systems.

Additional local commands for working from `assessment.json`:

```bash
estate-triage preview-top-findings --assessment-json outputs/assessment.json --top-n 10
estate-triage missing-evidence --assessment-json outputs/assessment.json
estate-triage explain-workload --assessment-json outputs/assessment.json --workload-key <key>
estate-triage describe-thresholds
estate-triage handoff-bundle --source-dir outputs/workflow --output outputs/handoff.zip
```

## Sanitized Corpus

Create a sanitized regression case from a bundle:

```bash
estate-triage sanitize-corpus \
  --bundle examples/estate-bundle \
  --output tests/corpus/example-case
```

Validate that a policy pack can load against the corpus:

```bash
estate-triage test-policy \
  --policy policy.yml \
  --corpus tests/corpus
```

Validate corpus structure before using it for policy regression:

```bash
estate-triage validate-corpus --corpus tests/corpus
```

This is the path for building a defensible golden corpus from real-world shapes while keeping raw customer data out of the repository.
