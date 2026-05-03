# Generated Data

The fixture generator creates complete synthetic input data for development, demos, tests, and policy validation.

```bash
gpu-rack-qualifier generate-fixtures \
  --output-dir generated/rackq-demo \
  --nodes 16 \
  --gpus-per-node 8 \
  --scenario mixed_commissioning \
  --seed 1
```

Generated files:

- `qualification_policy.yml`
- `node_inventory.yml`
- `business_assumptions.yml`
- `scenario_manifest.csv`
- `evidence/<node>/nccl_single_node_all_reduce.txt`
- `evidence/<node>/nccl_pairwise_all_reduce.csv`
- `evidence/<node>/nvidia_smi_topo_m.txt`
- `evidence/<node>/nvidia_smi_topo_p2p_n.txt`
- `evidence/<node>/nvidia_smi_query.xml`
- `evidence/<node>/bmc_sensors.redfish.json`
- `expected/slurm_node_labels.csv`
- `expected/quarantine.csv`
- `expected/review_queue.csv`
- `expected/slurm_features.conf.snippet`
- `expected/drain_review.sh`
- `expected/summary.json`
- `expected/evidence_bundle.json`

Scenarios:

- `pass`: complete evidence with multi-node training label candidates
- `missing_pairwise_nccl`: no pairwise NCCL evidence for multi-node labeling
- `weak_pairwise`: weak pairwise NCCL and weak topology paths
- `topology_weak_path`: topology-only weak GPU-GPU path evidence
- `topology_review_path`: topology review path evidence
- `sensor_warning`: BMC health warning and temperature warning
- `correctness_error`: NCCL correctness failure marker
- `wrong_count`: NCCL nonzero wrong count
- `timeout`: NCCL timeout marker
- `missing_gpu`: fewer GPUs than inventory expects
- `vbios_mismatch`: within-node VBIOS mismatch
- `cuda_drift`: CUDA version mismatch
- `ecc_mismatch`: ECC mode mismatch
- `mig_mismatch`: MIG mode mismatch
- `missing_topology`: required topology evidence missing
- `malformed_nccl`: NCCL evidence present but malformed
- `malformed_xml`: `nvidia-smi -q -x` evidence present but malformed
- `rack_wide_slow_baseline`: all generated nodes have slow peer-relative baseline evidence
- `partial_evidence`: missing pairwise NCCL evidence
- `bmc_critical`: BMC critical health without temperature threshold crossing
- `temperature_warning`: temperature above warning threshold
- `temperature_critical`: temperature above critical threshold
- `sensor_critical`: BMC critical health and temperature critical
- `fan_failure`: fan sensor failure
- `driver_drift`: driver version mismatch
- `mixed_commissioning`: deterministic mix of the above

The generator uses generic node names and generic GPU product names.

`scenario_manifest.csv` is the demo map. It explains which synthetic condition was assigned to each node, the expected evidence signal, the operator concern, and the business-impact angle. This keeps demos honest: the expected story is visible before qualification is run.

`business_assumptions.yml` contains operator-supplied assumptions used only for optional value-at-risk math:

```yaml
gpus_per_node: 8
hours_at_risk: 24
accelerator_hour_value: 3.5
release_goal: multinode_training
```

The tool does not invent financial value. These assumptions only translate qualification counters into the operator's own internal model.
