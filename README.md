# Sovereign Cloud

Local-first preflight tools that turn messy infrastructure evidence into reviewable decisions before teams commit migration, resilience, security, or capacity engineering time.

Each subdirectory is a standalone project with its own README, examples, tests, and package metadata. The common pattern is simple: ingest ordinary exports or evidence, normalize them, apply deterministic rules, and produce decision artifacts that help humans decide what to do next.

## Projects

| Project | What It Does |
|---|---|
| `brownout-policy-compiler` | Turns DDoS overload events and service priorities into a time-boxed brownout decision package with approvals, operator actions, and rollback. |
| `cabinet-burst-envelope` | Turns cabinet power and thermal telemetry into a conservative review lane for high-density workload placement conversations. |
| `dr-prereq-lint` | Finds missing recovery prerequisites by comparing protected systems against DNS dependency evidence before a DR test burns time. |
| `estate-triage` | Turns infrastructure, backup, and utilization exports into ranked discovery motions for migration, archive, rightsizing, and DR-tier review. |
| `gpu-rack-qualifier` | Converts GPU topology, NCCL, and sensor evidence into scheduler-facing labels, quarantine recommendations, and operator work queues. |
| `host-screen-contracts` | Turns recorded host-screen traces into API contract candidates, replay evidence, drift findings, and wrapper-readiness packages. |
| `inference-placement-bench` | Benchmarks candidate inference endpoints against workload constraints, reliability thresholds, and unit economics before integration work starts. |
| `prompt-egress-guard` | Scans prompts before submission to configured public-AI sites and produces deterministic allow, warn, redirect, or block decisions for rollout review. |
| `rag-permission-canary` | Tests RAG and AI-search permission boundaries with canary fixtures that catch forbidden evidence in answers, citations, snippets, metadata, and context. |
| `s3-compat-replay` | Mines observed S3 usage and runs safe synthetic probes to expose object-storage semantic mismatches before cutover. |
| `stateful-storage-fit` | Checks whether a VM workload's observed Linux storage shape can plausibly fit declared PersistentVolume options. |

## Design Principles

- Local-first by default.
- Deterministic rule engines over opaque scoring.
- Review packets over automatic production changes.
- Synthetic examples and redaction paths for safe sharing.
- Evidence provenance, caveats, and owner routing built into outputs.

## What This Repository Is Not

This is not a cloud control plane, deployment platform, pricing engine, monitoring system, orchestration layer, compliance certification product, or AI recommendation system.

The tools are intentionally scoped: they help teams decide where to look, what to validate, what to route to owners, and what should block or proceed to the next review stage.

## Demo Documents

Business-story and demo writeups are collected in `demodocs/`.

## Notes

- Each project can be used independently.
- Generated outputs, dependency folders, caches, and build artifacts are ignored.
- Individual projects keep their own licensing, package metadata, and test suites.
