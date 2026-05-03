# Policy Authoring

Policies should encode site thresholds and review posture without hardcoding product peak bandwidth claims.

## NCCL

Use absolute thresholds only when operators supply them:

```yaml
nccl:
  min_single_node_busbw_gbps: null
  min_pairwise_busbw_gbps: 250
  peer_median_warning_pct: 75
  peer_median_fail_pct: 50
```

When absolute single-node bandwidth is `null`, peer median comparison is used where possible. Peer-relative thresholds can hide rack-wide underperformance, so keep caveats in reports.

## Topology

Topology is context, not performance proof:

```yaml
topology:
  require_nvlink_for_multinode_training: false
  weak_gpu_gpu_paths:
    - SYS
    - PHB
  review_gpu_gpu_paths:
    - PXB
```

Do not require NVLink unless it is actually a policy requirement for the target fleet.

## Firmware

Firmware and driver mismatch actions should match site risk tolerance:

```yaml
firmware:
  require_driver_consistency_across_rack: true
  require_vbios_consistency_within_node: true
  driver_mismatch_action: REVIEW
  vbios_mismatch_action: DRAIN_REVIEW
```

## Sensors

Critical sensor states should be stronger than performance anomalies:

```yaml
sensors:
  health_warning_action: REVIEW
  health_critical_action: QUARANTINE
  fan_failure_action: QUARANTINE
  temp_warning_celsius: 80
  temp_critical_celsius: 90
```

Sensor snapshots are point-in-time evidence. Missing sensor data is not evidence of normal hardware state.
