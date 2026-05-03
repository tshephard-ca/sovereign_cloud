# Operator Playbook

This playbook keeps `gpu-rack-qualifier` local, offline, and review-only.

## 1. Prepare Inputs

Required input categories:

- node inventory YAML
- qualification policy YAML
- optional business assumptions YAML
- per-node evidence directories
- single-node NCCL all-reduce output
- pairwise NCCL CSV for multi-node labels
- `nvidia-smi topo -m` output
- optional `nvidia-smi topo -p2p n` output
- `nvidia-smi -q -x` XML
- exported BMC sensor JSON

Use generated fixtures to validate the workflow before using operational evidence:

```bash
gpu-rack-qualifier generate-fixtures \
  --output-dir generated/rackq-demo \
  --nodes 64 \
  --gpus-per-node 8 \
  --scenario mixed_commissioning \
  --seed 7
```

For the shortest reviewable flow, use a runbook:

```bash
gpu-rack-qualifier qualify --runbook examples/runbook.yml
```

## 2. Plan Pairwise NCCL Inputs

The tool can generate a pairwise plan and a reviewable batch template. It does not submit work.

```bash
gpu-rack-qualifier generate-pairwise-plan \
  --node-inventory generated/rackq-demo/node_inventory.yml \
  --output-csv out/pairwise_plan.csv \
  --strategy pairwise

gpu-rack-qualifier generate-sbatch-template \
  --plan-csv out/pairwise_plan.csv \
  --output-script out/pairwise_nccl_template.sh \
  --nccl-all-reduce /opt/nccl-tests/build/all_reduce_perf
```

Review the generated script before use. The script is not executable by default.

## 3. Qualify Evidence

```bash
gpu-rack-qualifier qualify \
  --evidence generated/rackq-demo/evidence \
  --node-inventory generated/rackq-demo/node_inventory.yml \
  --policy generated/rackq-demo/qualification_policy.yml \
  --business-assumptions generated/rackq-demo/business_assumptions.yml \
  --output-labels out/slurm_node_labels.csv \
  --output-quarantine out/quarantine.csv \
  --output-review-queue out/review_queue.csv \
  --output-slurm-fragment out/slurm_features.conf.snippet \
  --output-drain-review out/drain_review.sh \
  --summary out/summary.json \
  --evidence-bundle out/evidence_bundle.json
```

Review:

- `slurm_node_labels.csv`
- `quarantine.csv`
- `review_queue.csv`
- `slurm_features.conf.snippet`
- `drain_review.sh`
- `summary.json`
- `evidence_bundle.json`

## 4. Build Portfolio And Handoff

```bash
gpu-rack-qualifier portfolio \
  --summary out/summary.json \
  --labels out/slurm_node_labels.csv \
  --quarantine out/quarantine.csv \
  --output-markdown out/rack_portfolio.md \
  --output-json out/rack_portfolio.json

gpu-rack-qualifier handoff-bundle \
  --output-zip out/rackq_handoff.zip \
  --labels out/slurm_node_labels.csv \
  --quarantine out/quarantine.csv \
  --review-queue out/review_queue.csv \
  --slurm-fragment out/slurm_features.conf.snippet \
  --drain-review out/drain_review.sh \
  --summary out/summary.json \
  --policy generated/rackq-demo/qualification_policy.yml \
  --evidence-bundle out/evidence_bundle.json \
  --markdown-summary out/rack_portfolio.md
```

## 5. Track Drift

```bash
gpu-rack-qualifier baseline-create \
  --summary out/summary.json \
  --labels out/slurm_node_labels.csv \
  --quarantine out/quarantine.csv \
  --output-baseline out/baseline.json

gpu-rack-qualifier drift-report \
  --baseline out/baseline.json \
  --current-summary out/summary.json \
  --current-labels out/slurm_node_labels.csv \
  --current-quarantine out/quarantine.csv \
  --output-json out/drift.json \
  --output-markdown out/drift.md
```

Drift mode highlights status changes, feature changes, new blockers, new warnings, and bandwidth regressions.

## Readiness Lanes

Use readiness lanes to explain scheduling posture without overclaiming:

- `MULTINODE_READY`: candidate for multi-node training, single-node training, and inference.
- `SINGLE_NODE_READY`: candidate for single-node work after review.
- `INFERENCE_ONLY`: candidate for inference only if site policy allows.
- `AVOID_MULTINODE`: avoid multi-node training placement until reviewed.
- `REVIEW_REQUIRED`: evidence or warnings require human review.
- `QUARANTINE_REVIEW`: review before normal scheduling.

`review_queue.csv` is the operator action queue. It excludes nodes that passed current evidence and focuses review time on nodes whose evidence creates placement risk.

## Review Boundary

The tool does not apply labels, drain nodes, submit jobs, query live BMCs, update firmware, reboot hosts, or call external services.
