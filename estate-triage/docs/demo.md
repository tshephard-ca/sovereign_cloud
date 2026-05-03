# Demo Walkthrough

The demo is built to show the full triage loop, not a perfect estate.

## Run

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

## What To Look At First

1. `out/workflow/executive-summary.md`
2. `out/workflow/business-worklist.csv`
3. `out/workflow/data-request-checklist.csv`
4. `out/workflow/evidence-packets.json`

The technical `out/top25.csv` is still useful, but it is not the main story.

## Input Story

The curated inputs contain five groups:

- `mig-*`: active protected workloads with enough evidence for migration discovery.
- `archive-*`: powered-off and stale workloads that should start an ownership and retention conversation.
- `rightsize-*`: high allocation with low utilization over a qualified sample window.
- `dr-*`: large protected workloads with low change rate, high restore-point count, or large backup footprint.
- `needs-*`, `identity-*`, and `snapshot-*`: examples where the right output is caution, not a confident recommendation.

This is deliberate. A useful triage tool must make non-presentable rows obvious.

## Output Story

The workflow pack should make three decisions clear:

- which workloads are strong candidates
- which workloads need more data
- which workloads should not be presented yet

The business worklist includes a recommended next step and a human question for every row. The evidence packet keeps the technical trace available for reviewers who need to understand how the decision was made.

## Business Impact

The practical value is reducing manual spreadsheet triage and preventing weak evidence from becoming a confident recommendation.

The demo should support a first discovery conversation:

- migration review with application and platform owners
- archive review with application owners and retention stakeholders
- rightsizing review with operations teams
- DR tier review with resilience owners
- source-data follow-up with whoever owns the exports

## What Not To Claim

Do not claim the demo proves migration readiness, backup recoverability, sizing approval, or cost savings. It shows a local evidence-backed triage workflow.
