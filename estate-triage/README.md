# estate-triage

`estate-triage` is a deterministic local CLI that turns messy infrastructure, backup, and utilization exports into a practical discovery work plan.

It helps answer one narrow business question:

> Which workloads are credible candidates for migration review, archive review, rightsizing review, or DR tier review, and what evidence is missing before those findings should be presented?

The output is not just a ranked VM list. The useful artifact is the workflow pack: motion queues, business questions, data requests, evidence packets, and a short executive summary.

## What It Does

- Reads local CSV exports for inventory, backup metadata, and optional utilization.
- Normalizes evidence into versioned records with row and column provenance.
- Resolves workload identity by UUID first, then normalized name.
- Computes deterministic feature signals such as change rate, backup-to-used ratio, stale restore points, snapshot presence, and utilization p95.
- Applies a small versioned policy pack to assign one primary review motion.
- Separates strong candidates from review candidates, needs-more-data rows, and do-not-present rows.
- Writes CSV, JSON, Markdown, and workflow artifacts that can drive a discovery conversation.

## What It Does Not Do

It does not migrate data, create migration waves, verify backups, price infrastructure, prove application readiness, orchestrate workloads, call external services, use AI, use proprietary SDKs, or connect to source platforms.

The language is intentionally careful: a workload can be a `MIGRATION_REVIEW` candidate, not migration-ready. A DR finding can indicate review value, not verified recoverability.

## Quickstart

Install locally:

```bash
python3 -m pip install -e ".[test]"
```

Run the curated demo:

```bash
estate-triage analyze \
  --inventory examples/inventory.csv \
  --backup examples/backup_export.csv \
  --utilization examples/utilization.csv \
  --output out/top25.csv \
  --summary out/summary.json \
  --assessment-json out/assessment.json

estate-triage workflow-pack \
  --assessment-json out/assessment.json \
  --output-dir out/workflow \
  --top-n 25
```

Open these first:

- `out/workflow/executive-summary.md`
- `out/workflow/business-worklist.csv`
- `out/workflow/data-request-checklist.csv`
- `out/workflow/evidence-packets.json`

The lower-level `out/top25.csv` and `out/assessment.json` remain available for audit, integration, and troubleshooting.

Run tests:

```bash
python3 -m pytest -q
```

## Demo Throughline

The default example estate is intentionally small and balanced. It includes:

- active protected workloads for migration review
- powered-off stale workloads for archive review
- utilization-backed oversized workloads for rightsizing review
- large low-change protected workloads for DR tier review
- rows with missing backup, missing used storage, name-only identity, and snapshot blockers

The point of the demo is not to make every row look good. The point is to show that the tool can say:

- this is presentable
- this needs more data
- this should not be presented yet
- this is the human question to ask next

See [docs/demo.md](docs/demo.md) for a guided walkthrough.

## Inputs

Inventory CSV:

```csv
VM,VM UUID,Powerstate,CPUs,Memory MiB,Provisioned MiB,In Use MiB,OS,Snapshot total MiB,CPU usage percent,Memory usage percent,Tags,Notes
mig-payments-api,inv-uuid-001,poweredOn,4,8192,153600,72000,Generic Linux,0,18,48,motion:migration;service:payments,steady protected app
```

Backup metadata CSV:

```csv
VM,VM UUID,backup_total_mib,latest_restore_point_utc,restore_point_count,avg_daily_change_mib
mig-payments-api,inv-uuid-001,86000,2026-04-29T02:00:00Z,14,320
```

Optional utilization CSV:

```csv
VM,VM UUID,sample_start_utc,sample_end_utc,cpu_avg_pct,cpu_p95_pct,memory_avg_pct,memory_p95_pct,sample_count
rightsize-dev-build,inv-uuid-007,2026-04-01T00:00:00Z,2026-04-15T00:00:00Z,2,3,18,22,336
```

Validate inputs before analysis:

```bash
estate-triage validate --input examples/inventory.csv --kind inventory
estate-triage validate --input examples/backup_export.csv --kind backup
estate-triage validate --input examples/utilization.csv --kind utilization
estate-triage inspect-schema --input examples/backup_export.csv
```

## Outputs

The workflow pack is the business-facing output:

- `executive-summary.md`: concise summary of candidate queues, evidence quality, and caveats.
- `business-worklist.csv`: one row per workload with owner persona, recommended next step, business question, presentation class, and reason codes.
- `data-request-checklist.csv`: missing evidence grouped by field, priority, affected workloads, and question to send back to the data owner.
- `work-queues.json`: structured queues by motion.
- `evidence-packets.json`: technical trace packets with top features, blockers, missing evidence, and business context.
- `ranking-mode-comparison.json`: deterministic comparison of ranking strategies.

The analyze command also writes:

- `top25.csv`: fixed-column technical ranking.
- `summary.json`: counts, schema versions, motion distribution, and business-impact counts.
- `assessment.json`: complete structured assessment with identity, feature, policy, and confidence traces.

Presentation classes:

- `strong_candidate`: enough evidence for a discovery conversation.
- `review_candidate`: usable signal, but a human should confirm a specific caveat.
- `needs_more_data`: do not use as a lead candidate until missing evidence is supplied.
- `do_not_present`: a blocking evidence issue makes the finding unsafe to present.

## Review Motions

- `MIGRATION_REVIEW`: active workload with enough protection and footprint evidence to discuss migration discovery.
- `ARCHIVE_REVIEW`: stale or powered-off workload that may belong in retention, retirement, or scope-exclusion discussion.
- `RIGHTSIZING_REVIEW`: allocation or utilization pattern worth reviewing before sizing assumptions are made.
- `DR_TIER_REVIEW`: backup footprint, retention, or restore-point pattern worth reviewing with resilience owners.

## Ranking Modes

- `balanced`: default; spreads top-N output across motions.
- `global`: highest scores first across all motions.
- `per_motion`: top N per motion.
- `confidence_first`: high-confidence findings first, then score.
- `blockers_first`: rows with blockers first.
- `missing_evidence_first`: rows with missing evidence first.

## Architecture

The core pipeline is intentionally small:

```text
source exports
  -> evidence adapters
  -> canonical evidence records
  -> identity resolver
  -> feature registry
  -> policy engine
  -> structured assessment
  -> presentation/workflow layer
```

The kernel remains auditable. The presentation layer adds business language without changing the scored facts.

Versioned contracts:

- evidence schema: `1.0.0`
- feature schema: `1.0.0`
- policy schema: `1.0.0`
- assessment schema: `1.0.0`
- trace schema: `1.0.0`

See [docs/architecture.md](docs/architecture.md).

## Bundles And Real-World Data

Estate Evidence Bundles package inputs, mappings, thresholds, privacy settings, output paths, and optional feedback:

```bash
estate-triage run-workflow examples/estate-bundle --top-n 25
```

Generate broad deterministic test data:

```bash
estate-triage generate-real-world-data \
  --output /tmp/estate-generated-bundle \
  --profile coverage \
  --overwrite
```

Use generated data for coverage tests and policy calibration, not as proof of field accuracy. See [docs/real_world_data.md](docs/real_world_data.md) and [docs/roadmap.md](docs/roadmap.md).

## Reason Codes

Core motion codes:

- `MIGRATION_REVIEW`
- `ARCHIVE_REVIEW`
- `RIGHTSIZING_REVIEW`
- `DR_TIER_REVIEW`

Evidence and risk codes:

- `RECENT_BACKUP`
- `LOW_CHANGE_RATE`
- `SMALL_STORAGE_FOOTPRINT`
- `SNAPSHOT_PRESENT`
- `NO_BACKUP_MATCH`
- `POWERED_OFF`
- `STALE_BACKUP`
- `STALE_INVENTORY_SEEN`
- `UNKNOWN_OS`
- `HIGH_ALLOCATED_CPU_REVIEW`
- `HIGH_ALLOCATED_MEMORY_REVIEW`
- `IDLE_CPU`
- `OVERSIZED_MEMORY`
- `UTILIZATION_WINDOW_QUALIFIED`
- `SPARSE_UTILIZATION_WINDOW`
- `LARGE_BACKUP_FOOTPRINT`
- `HIGH_BACKUP_TO_USED_RATIO`
- `MANY_RESTORE_POINTS`
- `RPO_REVIEW`

Blocking and review flags include missing backup matches, missing used storage, missing change rate, name-only matching, duplicate candidates, identity conflicts, snapshots, and sparse utilization windows.

## Privacy

The CLI runs locally. It has no telemetry and makes no external calls.

Use `--redact` for shareable assessment and CSV outputs. Redaction replaces workload names with `workload_###` and hashes workload keys and UUIDs to 12 hex characters. Bundle workflow output is redacted according to the bundle privacy profile.

Examples and tests are synthetic.

## Data Honesty Caveats

- Allocation is not utilization.
- Backup size is not business criticality.
- Low change rate does not prove low risk.
- Powered off does not prove unused.
- A successful assessment does not prove migration readiness.
- A DR tier finding does not prove recoverability.
- A rightsizing finding does not authorize a resource change by itself.
- A missing-data finding is useful because it prevents weak evidence from becoming a confident recommendation.

## Roadmap

The near-term roadmap is documented in [docs/roadmap.md](docs/roadmap.md). The intended direction is better real-export calibration, richer workflow handoff artifacts, stronger policy-regression corpora, and optional adapter packages. Core behavior remains local, deterministic, and free of source-system API dependencies.
