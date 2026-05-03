# Architecture

`gpu-rack-qualifier` is organized around one offline pipeline:

```text
ingest -> parse -> derive features -> decide readiness -> compute impact -> render outputs
```

## Ingest

The CLI reads a node inventory, a qualification policy, optional business assumptions, and a per-node evidence directory. The core path does not call live BMCs, scheduler APIs, network services, or external services.

## Parse

Parser modules normalize user-supplied evidence:

- `parse_nccl.py`
- `parse_nvidia_smi_topo.py`
- `parse_nvidia_smi_query.py`
- `parse_bmc_snapshot.py`

The parsers preserve missing and malformed evidence as review signals. Missing evidence is not treated as normal hardware state.

## Derive Features

`features.py` converts parsed evidence into deterministic node features: GPU count, driver and CUDA versions, VBIOS consistency, NCCL bandwidth, weak pairwise counts, topology path counts, BMC sensor state, confidence, reason codes, blockers, warnings, and operator questions.

## Decide Readiness

`rules.py` classifies nodes into qualification statuses. `readiness.py` maps those statuses into human-facing workload-readiness lanes:

- `MULTINODE_READY`
- `SINGLE_NODE_READY`
- `INFERENCE_ONLY`
- `AVOID_MULTINODE`
- `REVIEW_REQUIRED`
- `QUARANTINE_REVIEW`

These lanes are review-only scheduling posture, not proof of workload success.

## Compute Impact

`impact.py` is the shared source for business-impact counters. Reports, summaries, evidence bundles, and portfolio views should use this model instead of recomputing separate versions of the same counts.

Operator-supplied assumptions can translate nodes withheld from multi-node training into estimated value at risk. The tool does not invent prices, utilization, or savings.

## Render Outputs

Output modules render the same decisions for different audiences:

- `report.py`: labels, quarantine rows, summary JSON, and Markdown report
- `action_queue.py`: prioritized review queue
- `slurm_render.py`: commented scheduler-facing Slurm snippets
- `portfolio.py`: rack-level review view
- `coverage_report.py`: evidence and signal coverage
- `baseline.py`: baseline and drift
- `evidence_bundle.py`: hash-backed handoff manifest
- `handoff.py`: ZIP bundle

`workflow.py` owns the main qualification orchestration so CLI commands, runbooks, demos, and tests use the same transformation path.
