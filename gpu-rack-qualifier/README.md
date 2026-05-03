# gpu-rack-qualifier

## What The Project Does

`gpu-rack-qualifier` is a local-first CLI that converts GPU communication, topology, and sensor evidence into scheduler-facing node labels and quarantine recommendations. It consumes NCCL all-reduce results, `nvidia-smi` topology and XML output, Redfish-like BMC sensor snapshots, optional inventory, and optional policy thresholds.

The product throughline is:

```text
GPU rack evidence -> workload-readiness lanes -> scheduler review artifacts -> operator action queue -> business-impact summary -> auditable handoff bundle
```

It writes reviewable outputs:

- Slurm node labels CSV
- quarantine and review CSV
- review queue CSV
- commented Slurm feature snippet
- commented drain-review script
- summary JSON
- workload-readiness and business-impact counters
- markdown explanation

## What The Project Does Not Do

It does not schedule jobs, manage Slurm, run cluster-wide tests, manage BMCs, update firmware, perform burn-in, prove reliability, or enforce quarantine. It does not call Slurm APIs, run `scontrol`, edit `slurm.conf`, submit jobs, reboot servers, connect to BMCs, store credentials, or call external services.

## Why This Exists

GPU clusters are expensive. Weak GPU links, NCCL correctness failures, firmware mismatches, missing GPUs, thermal warnings, or bad multi-node placement can waste costly accelerator capacity. Operators need a small bridge between qualification data and scheduler-consumable labels.

## Quickstart

```bash
gpu-rack-qualifier qualify \
  --evidence examples/evidence/ \
  --node-inventory examples/node_inventory.yml \
  --policy examples/qualification_policy.yml \
  --business-assumptions examples/business_assumptions.yml \
  --output-labels out/slurm_node_labels.csv \
  --output-quarantine out/quarantine.csv \
  --output-review-queue out/review_queue.csv \
  --output-slurm-fragment out/slurm_features.conf.snippet \
  --output-drain-review out/drain_review.sh \
  --summary out/summary.json \
  --evidence-bundle out/evidence_bundle.json
```

Then create a markdown explanation:

```bash
gpu-rack-qualifier explain \
  --summary out/summary.json \
  --labels out/slurm_node_labels.csv \
  --quarantine out/quarantine.csv \
  --output-markdown out/qualification_summary.md
```

Validate evidence without writing outputs:

```bash
gpu-rack-qualifier validate-evidence --evidence examples/evidence/
```

The same workflow can be expressed with a runbook:

```bash
gpu-rack-qualifier qualify --runbook examples/runbook.yml
```

Generate a complete demo rack, run qualification, produce reports, and create a handoff bundle:

```bash
gpu-rack-qualifier demo \
  --output-dir out/demo-rack-64 \
  --nodes 64 \
  --gpus-per-node 8 \
  --scenario mixed_commissioning \
  --seed 7 \
  --force
```

## Complete Input Data Generation

The project includes a deterministic fixture generator so users can create complete input data before they have production evidence wired in:

```bash
gpu-rack-qualifier generate-fixtures \
  --output-dir generated/rackq-demo \
  --nodes 64 \
  --gpus-per-node 8 \
  --scenario mixed_commissioning \
  --seed 7
```

The generated tree contains:

```text
generated/rackq-demo/
  qualification_policy.yml
  node_inventory.yml
  scenario_manifest.csv
  business_assumptions.yml
  evidence/
    node001/
      nccl_single_node_all_reduce.txt
      nccl_pairwise_all_reduce.csv
      nvidia_smi_topo_m.txt
      nvidia_smi_topo_p2p_n.txt
      nvidia_smi_query.xml
      bmc_sensors.redfish.json
  expected/
    slurm_node_labels.csv
    quarantine.csv
    slurm_features.conf.snippet
    drain_review.sh
    summary.json
    review_queue.csv
    evidence_bundle.json
```

Supported generated scenarios:

- `mixed_commissioning`
- `pass`
- `missing_pairwise_nccl`
- `weak_pairwise`
- `topology_weak_path`
- `topology_review_path`
- `sensor_warning`
- `correctness_error`
- `wrong_count`
- `timeout`
- `missing_gpu`
- `vbios_mismatch`
- `cuda_drift`
- `ecc_mismatch`
- `mig_mismatch`
- `missing_topology`
- `malformed_nccl`
- `malformed_xml`
- `rack_wide_slow_baseline`
- `partial_evidence`
- `bmc_critical`
- `temperature_warning`
- `temperature_critical`
- `sensor_critical`
- `fan_failure`
- `driver_drift`

The generator is deterministic for a given seed and does not use real provider, customer, or server-vendor names.

## Business-Impact Workflow

Generate or collect evidence, then run qualification:

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

Create a rack portfolio:

```bash
gpu-rack-qualifier portfolio \
  --summary out/summary.json \
  --labels out/slurm_node_labels.csv \
  --quarantine out/quarantine.csv \
  --output-markdown out/rack_portfolio.md \
  --output-json out/rack_portfolio.json
```

Create a baseline and compare a later run:

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

Create a review handoff bundle:

```bash
gpu-rack-qualifier handoff-bundle \
  --output-zip out/rackq_handoff.zip \
  --labels out/slurm_node_labels.csv \
  --quarantine out/quarantine.csv \
  --review-queue out/review_queue.csv \
  --slurm-fragment out/slurm_features.conf.snippet \
  --drain-review out/drain_review.sh \
  --summary out/summary.json \
  --policy examples/qualification_policy.yml \
  --evidence-bundle out/evidence_bundle.json \
  --markdown-summary out/qualification_summary.md
```

The summary JSON includes business-impact counters:

- multi-node-ready nodes
- evidence coverage percentage
- nodes without a multi-node training label
- avoid-multinode nodes
- inference-only nodes
- action-queue nodes
- quarantine-review nodes
- nodes with blockers
- nodes with warnings
- review questions generated

If `--business-assumptions` or the `demo` command supplies `gpus_per_node`, `hours_at_risk`, and `accelerator_hour_value`, the summary also includes an operator-supplied estimated value at risk. The tool does not invent prices or savings.

## Evidence Files

Each node is represented by a subdirectory under the evidence directory.

```text
evidence/
  gpu001/
    nccl_single_node_all_reduce.txt
    nccl_pairwise_all_reduce.csv
    nvidia_smi_topo_m.txt
    nvidia_smi_topo_p2p_n.txt
    nvidia_smi_query.xml
    bmc_sensors.redfish.json
```

`nccl_single_node_all_reduce.txt` is raw or lightly normalized `all_reduce_perf` output. The parser prefers `busbw` over `algbw`, detects nonzero wrong counts, timeout markers, and correctness errors, and scores only message sizes at or above the policy minimum.

`nccl_pairwise_all_reduce.csv` is user-supplied multi-node NCCL evidence. The MVP reads it; it does not launch MPI or submit jobs.

`nvidia_smi_topo_m.txt` is `nvidia-smi topo -m` output. GPU-to-GPU and GPU-to-NIC path classes are parsed when present.

`nvidia_smi_topo_p2p_n.txt` is optional `nvidia-smi topo -p2p n` output. Missing P2P capability can become a warning when policy expects it.

`nvidia_smi_query.xml` is `nvidia-smi -q -x` output. The parser uses the standard XML parser and tolerates missing fields.

`bmc_sensors.redfish.json` is a user-exported Redfish-like sensor snapshot. The tool does not connect to a live BMC.

## Local Collection Helper

`collect-local` may collect evidence from the current node only:

```bash
gpu-rack-qualifier collect-local \
  --node-name gpu001 \
  --output-dir evidence/gpu001/ \
  --nvidia-smi /usr/bin/nvidia-smi \
  --nccl-all-reduce /opt/nccl-tests/build/all_reduce_perf \
  --run-single-node-nccl \
  --timeout-seconds 300
```

The helper is local node only. It uses no SSH, no Slurm job submission, no BMC collection, no remote execution, and no network APIs. It does not bundle `nccl-tests` or `nvidia-smi`. If the NCCL binary is missing, it records `NCCL_BINARY_NOT_FOUND`.

## Pairwise Test Planning

The core does not launch multi-node tests, but it can generate reviewable input files for operators:

```bash
gpu-rack-qualifier generate-pairwise-plan \
  --node-inventory examples/node_inventory.yml \
  --output-csv out/pairwise_plan.csv \
  --strategy pairwise \
  --gpus-per-node 8

gpu-rack-qualifier generate-sbatch-template \
  --plan-csv out/pairwise_plan.csv \
  --output-script out/pairwise_nccl_template.sh \
  --nccl-all-reduce /opt/nccl-tests/build/all_reduce_perf \
  --gpus-per-node 8
```

The generated script is not submitted and is not executable by default. Operators must review partition names, node names, launch settings, and site policy.

## Import Helpers

Normalize an exported BMC snapshot:

```bash
gpu-rack-qualifier import-bmc-snapshot \
  --input-json evidence/gpu001/bmc_sensors.redfish.json \
  --output-json out/bmc.normalized.json
```

Convert a simple inventory CSV to `node_inventory.yml`:

```bash
gpu-rack-qualifier import-inventory-csv \
  --input-csv inventory.csv \
  --output-yml out/node_inventory.yml \
  --cluster-id cluster_001 \
  --rack-id rack_001
```

Expected CSV columns:

```text
name,rack,expected_gpu_count,expected_nic_count,expected_role,expected_features,maintenance_window
```

List-style fields may use commas or `|`.

## Output Interpretation

`PASS` means qualification evidence supports normal scheduler-facing labels from the supplied evidence.

`REVIEW` means evidence is incomplete or has warnings.

`INFERENCE_ONLY` means training placement is not recommended from current evidence.

`AVOID_MULTINODE` means single-node use may be acceptable but multi-node training should avoid the node.

`QUARANTINE` means the node should not be scheduled until humans review the blockers.

None of these are guarantees.

The human-facing readiness lanes are:

- `MULTINODE_READY`: candidate for multi-node training, single-node training, and inference.
- `SINGLE_NODE_READY`: candidate for single-node work after review.
- `INFERENCE_ONLY`: candidate for inference only if site policy allows.
- `AVOID_MULTINODE`: avoid multi-node training placement until reviewed.
- `REVIEW_REQUIRED`: evidence or warnings require human review.
- `QUARANTINE_REVIEW`: review before normal scheduling.

Use careful interpretations:

- multi-node training OK candidate
- single-node training OK candidate
- inference OK candidate
- avoid multi-node training candidate
- drain review recommended
- quarantine review recommended
- human review required

## Slurm Integration Boundary

All Slurm-facing output is review-only. Snippets are commented. Drain commands are commented. No Slurm changes are applied. Operators must review site policy before applying labels.

The Slurm feature snippet starts with warnings that it was not applied. The drain review script is not executable by default, and every `scontrol` command line is commented out.

`review_queue.csv` is the recommended human action queue. It excludes normal `PASS` nodes and prioritizes nodes with quarantine, weak-link, incomplete-evidence, or review-only findings.

## Evidence Bundle

`--evidence-bundle` writes a versioned manifest containing:

- tool version
- policy hash
- inventory hash
- evidence file paths, sizes, and SHA-256 hashes
- node qualification status
- confidence
- labels
- reason codes
- blockers
- warnings
- policy decision traces
- business-impact counters

This file is meant for archive, review, drift comparison, and handoff. It does not contain live credentials.

## Local Verification

Run the full local check:

```bash
bash scripts/check.sh
```

This runs the pytest suite and qualifies every generated scenario:

- pass
- missing pairwise NCCL
- weak pairwise
- topology weak path
- topology review path
- sensor warning
- correctness error
- wrong count
- timeout
- missing GPU
- VBIOS mismatch
- CUDA drift
- ECC mismatch
- MIG mismatch
- missing topology
- malformed NCCL
- malformed XML
- rack-wide slow baseline
- partial evidence
- BMC critical
- temperature warning
- temperature critical
- sensor critical
- fan failure
- driver drift
- mixed commissioning

## Additional Docs

- [Operator playbook](docs/operator_playbook.md)
- [Generated data](docs/generated_data.md)
- [Evidence bundle schema](docs/evidence_bundle_schema.md)
- [Policy authoring](docs/policy_authoring.md)
- [Demo walkthrough](docs/demo_walkthrough.md)
- [Architecture](docs/architecture.md)
- [Business cases](docs/business_cases.md)

## Reason-Code Dictionary

Evidence reason codes:

- `EVIDENCE_COMPLETE`
- `EVIDENCE_PARTIAL`
- `NCCL_SINGLE_NODE_PRESENT`
- `NCCL_SINGLE_NODE_MISSING`
- `NCCL_PAIRWISE_PRESENT`
- `NCCL_PAIRWISE_MISSING`
- `TOPO_PRESENT`
- `TOPO_MISSING`
- `NVIDIA_SMI_QUERY_PRESENT`
- `NVIDIA_SMI_QUERY_MISSING`
- `BMC_SNAPSHOT_PRESENT`
- `BMC_SNAPSHOT_MISSING`
- `INVENTORY_PRESENT`
- `INVENTORY_MISSING`

NCCL reason codes:

- `NCCL_SINGLE_NODE_PASS`
- `NCCL_SINGLE_NODE_WARN`
- `NCCL_SINGLE_NODE_FAIL`
- `NCCL_PAIRWISE_PASS`
- `NCCL_PAIRWISE_WEAK`
- `NCCL_PAIRWISE_TIMEOUT`
- `NCCL_CORRECTNESS_ERROR`
- `NCCL_WRONG_COUNT_NONZERO`
- `NCCL_PARSE_FAILED`
- `NCCL_BELOW_PEER_MEDIAN_WARNING`
- `NCCL_BELOW_PEER_MEDIAN_FAIL`
- `NCCL_NO_PEER_MEDIAN`
- `NCCL_SMALL_SAMPLE`

Topology reason codes:

- `TOPO_NVLINK_PRESENT`
- `TOPO_WEAK_GPU_PATH`
- `TOPO_REVIEW_GPU_PATH`
- `TOPO_P2P_NVLINK_MISSING`
- `TOPO_PARSE_FAILED`
- `TOPO_NOT_USED_FOR_FAILURE`

Hardware reason codes:

- `GPU_COUNT_OK`
- `GPU_COUNT_MISSING`
- `GPU_COUNT_BELOW_EXPECTED`
- `DRIVER_VERSION_OK`
- `DRIVER_VERSION_MISMATCH`
- `CUDA_VERSION_MISMATCH`
- `VBIOS_CONSISTENT`
- `VBIOS_MISMATCH`
- `MIG_MODE_MISMATCH`
- `ECC_MODE_MISMATCH`
- `RETIRED_PAGES_OBSERVED`
- `CLOCK_THROTTLE_OBSERVED`

Sensor reason codes:

- `BMC_HEALTH_OK`
- `BMC_HEALTH_WARNING`
- `BMC_HEALTH_CRITICAL`
- `BMC_FAN_FAILURE`
- `BMC_TEMP_WARNING`
- `BMC_TEMP_CRITICAL`
- `BMC_POWER_WARNING`
- `BMC_POWER_CRITICAL`
- `BMC_SENSOR_PARSE_FAILED`

Label and action reason codes:

- `LABEL_MULTI_NODE_TRAINING_OK`
- `LABEL_SINGLE_NODE_TRAINING_OK`
- `LABEL_INFERENCE_OK`
- `LABEL_AVOID_MULTINODE`
- `LABEL_REVIEW`
- `LABEL_QUARANTINE`
- `DRAIN_REVIEW_RECOMMENDED`
- `DO_NOT_DRAIN_AUTOMATICALLY`
- `REVIEW_ONLY_OUTPUT`
- `NO_LIVE_SLURM_CHANGE`

Blockers:

- `NCCL_CORRECTNESS_ERROR`
- `NCCL_TIMEOUT`
- `NCCL_WRONG_COUNT_NONZERO`
- `GPU_COUNT_BELOW_EXPECTED`
- `BMC_HEALTH_CRITICAL`
- `BMC_FAN_FAILURE`
- `BMC_TEMP_CRITICAL`
- `VBIOS_MISMATCH_DRAIN_POLICY`
- `TOPOLOGY_REQUIRED_BUT_MISSING`
- `NCCL_REQUIRED_BUT_MISSING`
- `HARDWARE_IDENTITY_UNKNOWN`
- `POLICY_INVALID`

Warnings:

- `NCCL_PAIRWISE_MISSING`
- `BMC_SNAPSHOT_MISSING`
- `TOPO_REVIEW_GPU_PATH`
- `DRIVER_VERSION_MISMATCH`
- `CUDA_VERSION_MISMATCH`
- `BMC_HEALTH_WARNING`
- `BMC_TEMP_WARNING`
- `PEER_MEDIAN_SMALL_SAMPLE`
- `NO_ABSOLUTE_THRESHOLD`
- `INVENTORY_MISSING`
- `PARTIAL_EVIDENCE`

## Data Honesty Caveats

- NCCL all-reduce is useful communication evidence, not a complete burn-in.
- One NCCL sample is not a full burn-in.
- Peer-relative thresholds can hide rack-wide underperformance.
- Absolute thresholds require user policy; the tool does not invent them.
- Topology evidence explains possible placement risk but does not by itself prove performance.
- BMC snapshots are point-in-time evidence.
- Missing sensor data does not prove hardware is fine.
- Slurm labels are recommendations until applied by administrators.
- Quarantine recommendations are not root-cause analysis.
- Inference-only does not guarantee suitability for every inference workload.
- Firmware mismatch may be harmless or serious depending on site policy.
- Scheduler labels do not guarantee workload success.

## Privacy And Security

The core tool is local-only. It has no telemetry, no external services, no credentials, no BMC logins, and no Slurm mutation.

Outputs may contain node names, serials, GPU UUIDs, rack IDs, and management identifiers. Use `--redact` before sharing outputs.

Redaction replaces node names, rack IDs, and cluster IDs with stable placeholders and hashes GPU UUIDs, serial-like identifiers, BMC hostnames, and management IPs where they appear in generated output. It preserves bandwidth values, statuses, labels, reason codes, blockers, warnings, and thresholds.

## Proprietary And Platform Boundary

The repo does not bundle `nccl-tests`. It does not bundle `nvidia-smi`. It does not bundle Slurm. It does not include vendor-specific BMC SDKs. Users supply their own evidence. Future live collectors must be optional adapters. Core logic remains vendor-neutral and offline-first.

## Expansion Roadmap

1. Slurm batch-script generator

   Generate a reviewable `sbatch` script for running pairwise `all_reduce_perf` tests. Do not submit the job.

2. Multi-node test planner

   Given a node list, propose a pairwise or ring test matrix:
   - same rack
   - cross rack
   - same switch
   - suspected weak peers

   Do not infer network topology without evidence.

3. DCGM diagnostic parser

   Optional parser for user-supplied GPU diagnostic output. Do not require DCGM in core.

4. Redfish collector adapter

   Separate optional package that collects Redfish sensor snapshots. It must handle credentials outside core and require explicit user consent.

5. Topology-aware Slurm constraint templates

   Generate suggested user-facing examples:
   - `--constraint=gpu_training_multinode_ok`
   - `--constraint=gpu_inference_ok`
   - `--constraint='gpu_training_single_node_ok&!gpu_avoid_multinode'`

   Do not change Slurm.

6. Rack portfolio mode

   Produce a rack-level summary:
   - multi-node training candidates
   - inference-only candidates
   - weak-link nodes
   - sensor-review nodes
   - firmware-review nodes
   - quarantine-review nodes

7. Handoff bundle

   Generate a ZIP containing:
   - labels CSV
   - quarantine CSV
   - Slurm snippet
   - drain review script
   - markdown summary
   - policy YAML
   - redacted evidence fingerprints

8. Policy packs

   Add preset threshold packs:
   - conservative training
   - inference-focused
   - commissioning
   - post-maintenance validation
   - mixed research cluster
   - commercial GPU cloud

   Policy packs only change thresholds and labels.

9. Drift mode

   Compare current qualification against prior qualification:
   - bandwidth regression
   - new weak peers
   - new firmware mismatch
   - new sensor warnings
   - topology change

10. Root-cause hints

    Add non-authoritative hints:
    - likely link issue
    - likely firmware mismatch
    - likely thermal issue
    - likely missing GPU

    These remain hints, not diagnoses.

11. Executor interface, separate package only

    A future separate package may apply Slurm labels or drain nodes.

    Core must not implement live mutation. Any executor must require explicit approval, dry run, change ticket metadata, rollback plan, and audit log.
