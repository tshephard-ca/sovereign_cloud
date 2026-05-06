# Demo docs: P&L-aware sovereign-cloud preflights

This directory shows how the repo's demos turn ordinary local evidence into review packets before a cloud provider, partner, or customer makes a commitment.

Use these demos before a migration, disaster recovery [DR] exercise, artificial intelligence [AI] rollout, capacity promise, modernization scope, or incident-readiness review. The goal is not to certify anything. The goal is to surface what may break, who owns the next action, and whether the risk is acceptable before revenue, margin, or trust is put at risk.

## Profit and loss lens

The demos are most useful when a technical miss would show up in the profit and loss [P&L] statement as one of these problems:

- **Revenue delay:** a migration, AI launch, recovery service, or modernization project cannot move forward.
- **Margin leakage:** senior engineers, architects, facility teams, or partner teams spend time on avoidable rework.
- **Capacity waste:** scarce GPU, cabinet, storage, or inference capacity is idle, misallocated, or promised too early.
- **Cost of sales creep:** weak opportunities consume discovery, evidence prep, and custom proposal time.
- **Renewal or trust risk:** a recovery test, permission boundary, or cutover fails in front of the customer.

The rough numbers below are illustrative only. Replace them with your own rates, margins, service pricing, and customer commitments.

Simple assumptions for demo conversations:

```text
Loaded technical labour:     $150-$250/hour
Small review loop:           5-10 people x 2-4 hours = ~$1.5k-$10k
Cutover or DR bridge:        6-12 people x 4-8 hours = ~$3.6k-$24k
Weak pre-sales opportunity:  20-40 hours = ~$3k-$10k
Capacity pool example:       1-5% avoidable idle on $250k/month = ~$2.5k-$12.5k/month
Two-person rework week:      80 hours = ~$12k-$20k
```

These are not savings claims. They are a fast way to decide whether a preflight is worth running.

## Start with the business commitment

| Before saying this | Open this demo | P&L reason | First output to show |
|---|---|---|---|
| “This app can move to our object store.” | `s3-compat-replay-demo` | Protect migration and repatriation revenue by catching S3 semantic gaps before rollback, emergency fixes, or customer-visible breakage. | Cutover brief: presigned URLs, CORS, Object Lock, ACLs, multipart, versioning, tags, metadata, and error shapes. |
| “This protected workload can recover.” | `dr-prereq-lint-demo` | Protect DR credibility and renewal value by finding missing shared prerequisites before the recovery window is spent debugging basics. | Owner worklist: DNS, identity, database, file, licence, remote access, and time-service gaps. |
| “This GPU capacity is ready to schedule.” | `gpu-rack-qualifier-demo` | Protect accelerator margin by keeping weak, miswired, drifting, or thermally risky nodes out of customer commitments. | Scheduler labels, quarantine queue, review reasons, and business-impact counters. |
| “This dense cabinet can absorb the next burst.” | `cabinet-burst-envelope-demo` | Avoid unsafe or wasteful expansion conversations before facility, sales engineering, or customer time is consumed. | Review lane: ready for facility review, needs remediation, stop expansion discussion, or collect evidence. |
| “This inference endpoint fits the workload.” | `inference-placement-bench-demo` | Avoid integrating against the wrong endpoint and exposing bad unit economics after traffic starts. | Recommendation using location, latency, streaming, throughput, reliability, and user-supplied economics. |
| “This AI search release is safe to expose.” | `rag-permission-canary-demo` | Reduce late launch friction and disclosure risk by testing permission boundaries before connector, index, prompt, or schema changes ship. | Permission regression report across answers, citations, snippets, metadata, and raw context. |
| “Employees can use public AI tools with guardrails.” | `prompt-egress-guard-demo` | Support AI adoption without turning unmanaged public AI tools into a new data-egress path. | Local allow, warn, redirect, or block decisions with redacted audit evidence. |
| “This estate is ready for deeper assessment.” | `estate-triage-demo` | Lower cost of sales by turning messy exports into qualified queues, missing-evidence requests, and do-not-present rows. | Executive summary, candidate queues, data requests, and work packets. |
| “This legacy transaction can be wrapped.” | `host-screen-contracts-demo` | Reduce modernization discovery and wrapper rework before partners or delivery teams touch the live host. | Transaction contract, OpenAPI candidate, replay evidence, drift report, and privacy report. |
| “This stateful VM can move to the target platform.” | `stateful-storage-fit-demo` | Avoid late storage blockers in container or platform modernization work. | PASS, REVIEW, or FAIL fit report against declared persistent-storage options. |
| “This overload plan protects the right services.” | `brownout-policy-compiler-demo` | Reduce incident decision latency and protect high-priority services before an overloaded bridge call starts. | Brownout decision package: protect, degrade, approval, blockers, rollback, and operator questions. |

## Highest-value demo paths

### 1. Repatriation and migration revenue

Open `estate-triage-demo`, then `s3-compat-replay-demo`, then `stateful-storage-fit-demo`.

This path is for the first serious customer or partner discussion after exports arrive. It helps answer: Which workloads are worth discussing, which object-store behaviours may break cutover, and which stateful workloads need storage review before a pilot.

P&L motivation: protect paid assessment time, reduce weak-opportunity drag, and avoid a cutover bridge that discovers problems after the commitment is public. A single weak opportunity can consume roughly 20-40 hours of architect, partner, and delivery time before anyone says no.

### 2. Recovery and trust

Open `dr-prereq-lint-demo`, then `brownout-policy-compiler-demo`.

This path is for providers selling resilience, backup, DR, incident readiness, or managed operations. It separates “we have backups” from “the service can recover,” and separates “we have mitigation tools” from “we know what to protect, degrade, approve, and roll back.”

P&L motivation: protect renewals and executive trust. A DR exercise or incident bridge involving 6-12 people for half a day can consume roughly $3.6k-$24k in labour before any customer-impact, downtime, or reputation cost is counted.

### 3. Sovereign AI capacity and margin

Open `gpu-rack-qualifier-demo`, `cabinet-burst-envelope-demo`, `inference-placement-bench-demo`, and `rag-permission-canary-demo`.

This path is for scarce AI capacity. It asks whether the nodes are schedulable, whether the cabinet evidence supports the next conversation, whether the endpoint fits the workload, and whether AI search respects permission boundaries.

P&L motivation: protect gross margin and capacity credibility. On a $250k/month capacity pool, even 1-5% avoidable idle time or misallocation is roughly $2.5k-$12.5k/month. The larger risk is promising capacity or AI behaviour before the evidence trail can survive review.

### 4. Partner-led modernization

Open `host-screen-contracts-demo`, then `stateful-storage-fit-demo`, then `prompt-egress-guard-demo` if AI-assisted work is part of discovery.

This path is for legacy systems, partner delivery, API candidates, and modernization scoping. It lets teams discuss transaction shape, privacy risk, replayability, drift, and storage fit before asking for privileged access or starting implementation.

P&L motivation: reduce discovery rework. A two-person rework week is roughly $12k-$20k at the simple labour assumptions above, before opportunity cost or project-delay cost is included.

## How to present the demos

Lead with the commitment, not the parser.

Good framing:

- “This creates a review packet before we commit.”
- “This identifies blockers and owner actions.”
- “This shows which evidence is missing.”
- “This is scoped proof for the next decision.”
- “This is review-only; it does not approve production change.”

Avoid:

- “certified sovereign”
- “compliant by default”
- “migration approved”
- “capacity guaranteed”
- “AI governance solved”
- “DR proven”

## Output pattern

Across the demos, the useful shape is consistent:

```text
Local evidence -> deterministic rules -> decision packet -> owner actions -> redacted handoff
```

Typical outputs include blockers, review lanes, owner worklists, approval queues, rollback checks, hashes, manifests, redacted bundles, and business-readable summaries.

## Add a new demo

Add a demo here only when it can answer seven questions:

1. What customer or partner commitment is being de-risked?
2. What local evidence is already available?
3. What late failure would hurt revenue, margin, capacity, or trust?
4. What decision does the demo produce?
5. Who owns the next action?
6. What can be safely redacted and shared?
7. What claim must the demo refuse to make?

Recommended structure:

```text
<project-name>-demo/
  README.md
  inputs/
  outputs/
  redacted/
  notes/
```

Strong demos do not imply trust. They make trust cheaper to review.
