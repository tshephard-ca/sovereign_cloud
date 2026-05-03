# Demo Walkthrough

This demo shows the core business story: use qualification evidence to decide which GPU nodes can be exposed to multi-node training, which should be constrained, and which need review before normal scheduling.

## 1. Generate And Qualify A Demo Rack

```bash
gpu-rack-qualifier demo \
  --output-dir out/demo-rack-64 \
  --nodes 64 \
  --gpus-per-node 8 \
  --scenario mixed_commissioning \
  --seed 7 \
  --force
```

The command writes:

- `node_inventory.yml`
- `qualification_policy.yml`
- `business_assumptions.yml`
- `scenario_manifest.csv`
- `evidence/`
- `run/slurm_node_labels.csv`
- `run/quarantine.csv`
- `run/review_queue.csv`
- `run/slurm_features.conf.snippet`
- `run/drain_review.sh`
- `run/summary.json`
- `run/qualification_summary.md`
- `run/rack_portfolio.md`
- `run/coverage.json`
- `run/business_impact.json`
- `run/evidence_bundle.json`
- `run/rackq_handoff.zip`

## 2. Read The Scenario Manifest

Open `scenario_manifest.csv` first. It explains the synthetic condition for each node and the expected operational concern. This makes the demo input accountable before any output is inspected.

## 3. Read The Qualification Summary

Open `run/qualification_summary.md`.

The first section should answer:

- how many nodes were seen
- how many are multi-node-ready candidates
- how many are withheld from multi-node training
- how many need action-queue review
- how much evidence coverage was available

## 4. Review The Action Queue

Open `run/review_queue.csv`.

This is the operator queue. It excludes normal pass nodes and focuses on nodes with placement risk:

- `P0`: quarantine-review candidates
- `P1`: avoid-multinode candidates
- `P2`: incomplete evidence, inference-only, or review-required candidates

## 5. Review Scheduler Artifacts

Open:

- `run/slurm_features.conf.snippet`
- `run/drain_review.sh`

Both are commented and review-only. The tool does not apply labels, drain nodes, submit jobs, or change scheduler state.

## 6. Read Coverage And Impact

Open:

- `run/coverage.json`
- `run/business_impact.json`

Coverage shows whether the evidence is complete enough to trust the qualification posture. Business impact translates review counters into operator-supplied value-at-risk assumptions without inventing financial claims.

## 7. Package The Handoff

`run/rackq_handoff.zip` packages review artifacts, schemas, docs, and scripts for support, operations, or stakeholder review.

## Demo Throughline

The demo is successful when a reviewer can say:

- these nodes are candidates for multi-node training
- these nodes should avoid multi-node training
- these nodes need quarantine review
- these evidence gaps limit confidence
- these questions should be answered next
- these artifacts can be handed to scheduler or operations reviewers

The demo does not prove workload success or root cause. It shows a deterministic pre-scheduling qualification workflow.
