# Sovereign Cloud

Local-first preflight tools that turn messy infrastructure evidence into reviewable decisions before teams commit migration, resilience, security, or capacity engineering time.

Each subdirectory is a standalone project with its own README, examples, tests, and package metadata. The common pattern is simple: ingest ordinary exports or evidence, normalize them, apply deterministic rules, and produce decision artifacts that help humans decide what to do next.

## Projects

These tools use cloud, infrastructure, and operations vocabulary. In plain terms, they are meant to reduce expensive surprises: failed migrations, unsafe capacity promises, bad AI rollouts, weak recovery tests, or late discovery of missing dependencies. Each one keeps the technical evidence visible while also producing a business-readable review artifact.

| Project | Technical Role | Why It Matters For A Cloud Company |
|---|---|---|
| `brownout-policy-compiler` | Turns DDoS overload events and service priorities into a time-boxed brownout decision package with approvals, operator actions, and rollback. | During severe overload, a cloud company may need to protect critical customer or control-plane services while temporarily degrading less critical paths. This tool makes that tradeoff explicit, reviewable, reversible, and owner-routed instead of improvised during an incident. |
| `cabinet-burst-envelope` | Turns cabinet power and thermal telemetry into a conservative review lane for high-density workload placement conversations. | AI and other dense workloads can create power and cooling risk before anyone notices at the service level. This helps facility, operations, and sales engineering teams avoid promising capacity until the cabinet evidence is strong enough for human review. |
| `dr-prereq-lint` | Finds missing recovery prerequisites by comparing protected systems against DNS dependency evidence before a DR test burns time. | Disaster-recovery tests often fail because a dependent resolver, identity service, database, file service, or license service was not included in scope. This tool helps find those gaps before teams spend a recovery window proving what could have been known earlier. |
| `estate-triage` | Turns infrastructure, backup, and utilization exports into ranked discovery motions for migration, archive, rightsizing, and DR-tier review. | Cloud migration and optimization work often starts with messy spreadsheets. This turns those exports into a practical worklist: which workloads look worth discussing, which need more evidence, which should not be presented yet, and which business questions owners must answer. |
| `gpu-rack-qualifier` | Converts GPU topology, communication, and sensor evidence into scheduler-facing labels, quarantine recommendations, and operator work queues. | GPU capacity is expensive and easy to waste if bad links, missing devices, thermal warnings, or topology issues reach users. This tool gives operators a reviewable bridge from qualification evidence to scheduler labels and remediation queues. |
| `host-screen-contracts` | Turns recorded host-screen traces into API contract candidates, replay evidence, drift findings, privacy findings, and wrapper-readiness packages. | Many high-value legacy transactions are still trapped behind terminal screens. This gives modernization teams a safer way to understand transaction shape and risk before committing to wrapper or API implementation work. |
| `inference-placement-bench` | Benchmarks candidate inference endpoints against workload constraints, reliability thresholds, location needs, and unit economics before integration work starts. | A cloud AI team needs to know which endpoint is a credible fit for a workload before routing production traffic. This tool makes latency, reliability, streaming, data-location, and cost tradeoffs visible in a review packet. |
| `prompt-egress-guard` | Scans prompts before submission to configured public-AI sites and produces deterministic allow, warn, redirect, or block decisions for rollout review. | Employees may paste source code, secrets, customer context, health-data-like text, or financial details into public AI tools. This provides a narrow browser-extension control that can redirect risky work to approved AI destinations without claiming to be full DLP or complete AI governance. |
| `rag-permission-canary` | Tests RAG and AI-search permission boundaries with canary fixtures that catch forbidden evidence in answers, citations, snippets, metadata, and context. | Permission leaks in RAG or AI search can expose restricted documents even when the answer looks harmless. This gives product and platform teams CI-friendly release evidence before connector, ACL-sync, index, model, prompt, or schema changes go live. |
| `s3-compat-replay` | Mines observed S3 usage and runs safe synthetic probes to expose object-storage semantic mismatches before cutover. | Copying objects is not enough if applications depend on tags, version IDs, CORS, presigned URLs, ACLs, multipart upload, Object Lock, headers, or error shapes. This tool helps catch those compatibility gaps before a migration or repatriation cutover. |
| `stateful-storage-fit` | Checks whether a VM workload's observed Linux storage shape can plausibly fit declared PersistentVolume options. | Stateful workloads are often the hardest part of moving VM applications to Kubernetes-style platforms. This helps platform and migration teams see whether access modes, volume behavior, capacity, and performance expectations are plausible before a pilot fails late. |

## Design Principles

- Local-first by default.
- Deterministic rule engines over opaque scoring.
- Review packets over automatic production changes.
- Synthetic examples and redaction paths for safe sharing.
- Evidence provenance, caveats, and owner routing built into outputs.

## What This Repository Is Not

This is not a cloud control plane, deployment platform, pricing engine, monitoring system, orchestration layer, compliance certification product, or AI recommendation system.

The tools are intentionally scoped: they help teams decide where to look, what to validate, what to route to owners, and what should block or proceed to the next review stage.

## Notes

- Each project can be used independently.
- Generated outputs, dependency folders, caches, and build artifacts are ignored.
- Individual projects keep their own licensing, package metadata, and test suites.
