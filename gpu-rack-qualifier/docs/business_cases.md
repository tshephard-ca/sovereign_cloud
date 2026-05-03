# Business Cases

`gpu-rack-qualifier` is useful when expensive GPU capacity needs evidence-based release decisions before broad scheduling.

## New Rack Commissioning

Physical install does not mean workload readiness. The tool separates nodes that are candidates for multi-node training from nodes that need inference-only placement, avoid-multinode placement, or quarantine review.

Business impact:

- earlier partial release of qualified capacity
- fewer failed commissioning cycles
- clearer punch list for operators and support teams
- less ambiguity between "powered on" and "ready for distributed training"

## Weak-Link Avoidance

A distributed training job can be limited by the weakest communication path. Pairwise NCCL and topology evidence help identify nodes that should not be treated as fully multi-node-ready.

Business impact:

- fewer slow or stalled distributed jobs
- clearer evidence for fabric or cabling review
- better scheduler constraints for expensive training workloads

## Correctness And Timeout Review

NCCL correctness failures, wrong counts, and timeouts are stronger than ordinary slowness. They can justify quarantine review before user workloads land on the node.

Business impact:

- lower risk of invalid training runs
- less model-team debugging time
- better evidence for hardware, driver, or fabric escalation

## Thermal, Fan, And Sensor Risk

BMC health, fan, power, and temperature snapshots are point-in-time signals, but they are useful before scheduling high-value jobs.

Business impact:

- fewer emergency drains
- stronger coordination with facilities teams
- clearer hardware support evidence

## Firmware And Software Drift

Driver, CUDA, VBIOS, ECC, and MIG differences can create support ambiguity. The tool turns drift into reason-coded review findings and scheduler-facing posture.

Business impact:

- faster remediation planning
- fewer surprise compatibility issues
- cleaner support handoff

## Evidence Coverage

Missing pairwise, topology, sensor, or hardware identity data should not quietly become confidence. Coverage reporting keeps acceptance and release decisions honest.

Business impact:

- fewer false-ready decisions
- clearer collection gaps
- stronger acceptance and audit trail

## Handoff And Redaction

The evidence bundle and handoff ZIP provide a compact review package. Redaction can hide operational identifiers while preserving counts, labels, reason codes, and review posture.

Business impact:

- faster support triage
- fewer repeated evidence requests
- easier stakeholder review

## Caveat

The tool creates review-only qualification evidence. It does not prove reliability, diagnose root cause, guarantee workload success, or apply scheduler state.
