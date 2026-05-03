# brownout-policy-compiler

## What the project does

`brownout-policy-compiler` is a local-only compiler that turns a normalized DDoS mitigation event and a service-priority map into a temporary brownout decision package with TTL and rollback.

It answers one question: given this event and this business service-priority map, what should the incident team protect now, what can be degraded under review, what needs approval, what is blocked, and what must be rolled back?

## What the project does not do

It does not detect DDoS attacks, scrub traffic, push firewall rules, change routers, call APIs, generate traffic, scan networks, or prove that a service is protected.

It is not a DDoS detector, scrubbing service, traffic generator, router controller, firewall manager, WAF, SD-WAN controller, customer portal, orchestration system, or attack tool.

## Why this exists

DDoS response is not only filtering bad traffic. During severe overload, organizations may need to preserve critical services while intentionally degrading lower-priority ones. A reviewable policy package helps network, security, and application teams agree on what to protect, what to restrict, and what to roll back.

## Quickstart

```bash
brownout-policy-compiler compile \
  --event examples/events/ddos_event.json \
  --services examples/service_priority.yml \
  --output-plan out/brownout_plan.yml \
  --output-actions out/actions.csv \
  --output-rollback out/rollback_plan.yml \
  --summary out/summary.json
```

The compiler also writes decision-focused artifacts next to `--summary` by default:

- `decision_brief.json`
- `decision_brief.md`
- `operator_queue.csv`
- `approval_queue.csv`
- `rollback_clock.json`
- `blocked_actions.json`

From a source checkout:

```bash
PYTHONPATH=src python3 -m brownout_policy_compiler compile \
  --event examples/events/ddos_event.json \
  --services examples/service_priority.yml \
  --output-plan out/brownout_plan.yml \
  --output-actions out/actions.csv \
  --output-rollback out/rollback_plan.yml \
  --summary out/summary.json \
  --incident-id INC-12345 \
  --now 2026-01-01T00:05:00Z
```

Validate inputs:

```bash
brownout-policy-compiler validate \
  --event examples/events/ddos_event.json \
  --services examples/service_priority.yml
```

Explain a generated plan:

```bash
brownout-policy-compiler explain \
  --plan out/brownout_plan.yml \
  --output-markdown out/brownout_summary.md
```

Generate a deterministic full-coverage offline lab bundle:

```bash
brownout-policy-compiler lab generate-bundle \
  --output-dir out/generated_full_coverage
```

This writes synthetic input data, compiled review packages, redacted input and output bundles, negative validation fixtures, a large-estate fixture, decision briefs, operator queues, approval queues, per-scenario markdown summaries, `coverage_report.json`, `realism_report.json`, and `gap_report.md`. The generated data is intended for local testing, demos, tabletop preparation, and implementation gap analysis. It does not use real customer, provider, vendor, or platform data.

`generate-data` remains available as a compatibility alias for existing scripts.

## Input and review workflows

Generate all starter input files needed for a review package:

```bash
brownout-policy-compiler init all \
  --output-dir out/input_seed
```

This writes a service-priority YAML file, trusted source profile, endpoint inventory CSV, approval matrix, rollback controls, policy pack, thresholds config, tabletop worksheet, and deterministic normalized event scenarios.

The generated service-priority data includes multi-endpoint services, region metadata, IPv6 and CIDR examples, explicit trusted-source applicability, service-specific business impact language, action-specific rollback controls, approval delegation metadata, and dependency/maintenance-window examples.

Generate one normalized event scenario:

```bash
brownout-policy-compiler generate event \
  --scenario application_payment_endpoint \
  --output out/input_seed/ddos_event.json
```

Write a scenario catalog or a tabletop worksheet:

```bash
brownout-policy-compiler generate scenario-catalog \
  --output out/input_seed/scenario_catalog.json

brownout-policy-compiler generate tabletop \
  --output out/input_seed/tabletop_worksheet.md
```

Score whether a service-priority file has enough business, ownership, approval, rollback, and endpoint metadata for useful incident review:

```bash
brownout-policy-compiler readiness \
  --services out/input_seed/service_priority.yml \
  --output out/readiness_report.json
```

Run a tabletop bundle from a normalized event and service-priority file:

```bash
brownout-policy-compiler tabletop \
  --event out/input_seed/events/01_volumetric_public_and_vpn.json \
  --services out/input_seed/service_priority.yml \
  --policy-pack out/input_seed/policy_pack.yml \
  --config out/input_seed/thresholds.yml \
  --output-dir out/tabletop_run
```

Compare a generated plan with operator-entered actual changes after an incident review:

```bash
brownout-policy-compiler post-incident-diff \
  --plan out/tabletop_run/brownout_plan.yml \
  --actual-changes out/post_incident_actual_changes.yml \
  --output out/post_incident_diff.json
```

These workflow commands remain local-only and review-only. They do not apply policy, invoke device commands, call APIs, or prove that traffic changed.

## Input: normalized DDoS event

The event input is JSON with `event_id`, `started_at` or `observed_at`, `severity`, `attack_class`, `mitigation_state`, and `targets`. Each target has a name, IP, protocol, ports, and optional observed and baseline metrics.

The core does not parse proprietary provider formats. It consumes normalized JSON only, so event adapters can remain optional and separate where API terms or licensing matter.

Unknown event fields are preserved as model metadata. Source countries, source ASNs, source prefixes, protocol mix, path anomalies, and spoofing likelihood are advisory evidence. The compiler does not say that an observed source prefix is malicious.

## Input: service-priority YAML

The service-priority YAML is the business contract. It defines:

- `P0` through `P4` priority, where `P0` is the most critical and `P4` is deferrable or low-priority.
- Brownout modes: `PROTECT`, `RESTRICT_TO_TRUSTED`, `RATE_LIMIT`, `SHED`, `ISOLATE`, and `NO_ACTION`.
- Trusted source groups with CIDR ranges.
- Service endpoints with IP or CIDR, protocol, and ports or port ranges.
- Allowed actions, which are a hard boundary for the compiler.
- TTL limits, approval requirements, and rollback requirements.

The compiler matches event targets to service endpoints by IP, protocol, and port overlap. It does not infer service ownership from names by default.

## Decision package outputs

The primary output is the decision package. It is meant for an incident bridge, tabletop, or post-incident review where people need to separate safe protection from risky degradation quickly.

- `decision_brief.json`: machine-readable first-read package with counts, business throughline, protect-now actions, degradation candidates, approval queue, blockers, operator questions, rollback clock, evidence quality, action groups, and assumptions.
- `decision_brief.md`: human-readable version of the same package, organized by decision queue before the raw action inventory.
- `operator_queue.csv`: ordered CSV for operators, with service, priority, risk, confidence, TTL, rollback deadline, owner, approver, rollback owner, operator question, and business impact.
- `approval_queue.csv`: subset of high-risk or approval-required actions.
- `rollback_clock.json`: rollback deadlines and action IDs that must be verified.
- `blocked_actions.json`: compiler blockers and their reasons.
- `brownout_plan.yml`: complete detailed plan for downstream review tools.
- `actions.csv`: complete action inventory.
- `rollback_plan.yml`: detailed rollback plan with owners, verification steps, and evidence requirements.
- `summary.json`: lint status, counts, warnings, blockers, distributions, and review reasons.

Use the decision package in this order:

1. Read the `business_throughline` and `first_read` counts.
2. Review `protect_now` actions for P0/P1 continuity paths.
3. Review `degrade_candidates` for lower-priority services that can absorb pressure.
4. Check `approval_queue` before any high-risk or approval-required action.
5. Check `blocked_actions` before discussing unsafe changes.
6. Track `rollback_clock` until every temporary action is verified closed.

## Output interpretation

`PASS` means a review-only policy package was generated with no blockers and no high or critical risk actions.

`REVIEW` means a package was generated but approval, uncertainty, high-risk actions, unmatched targets, or warnings require human review.

`FAIL` means the package should not be used because validation or safety checks failed.

None of these mean the actions were applied.

## Reason-code dictionary

Reason codes:

- `TARGET_UNDER_ATTACK`
- `TARGET_NOT_UNDER_ATTACK`
- `TARGET_MATCHED_SERVICE`
- `UNMAPPED_ATTACK_TARGET`
- `TARGET_MATCHES_MULTIPLE_SERVICES`
- `EVENT_TARGET_PORTS_MISSING`
- `CIDR_ENDPOINT_MATCH`
- `P0_SERVICE_PROTECTED`
- `P1_SERVICE_PROTECTED`
- `LOW_PRIORITY_SERVICE`
- `TRUSTED_SOURCES_AVAILABLE`
- `TRUSTED_SOURCES_MISSING`
- `TEMPORARY_TTL_APPLIED`
- `ROLLBACK_REQUIRED`
- `APPROVAL_REQUIRED`
- `SOURCE_BLOCKING_DISABLED_BY_DEFAULT`
- `SOURCE_BLOCKING_DISABLED_SPOOFING_LIKELY`
- `NULL_ROUTE_DISABLED_BY_DEFAULT`
- `NULL_ROUTE_ALLOWED_BY_FLAG`
- `NULL_ROUTE_COLLATERAL_RISK`
- `SHED_ALLOWED_BY_SERVICE_POLICY`
- `SHED_BLOCKED_FOR_HIGH_PRIORITY`
- `RATE_LIMIT_ALLOWED_BY_SERVICE_POLICY`
- `RATE_LIMIT_PROFILE_SELECTED`
- `CHALLENGE_SELECTED_FOR_APPLICATION_ATTACK`
- `PRIORITIZE_SELECTED_FOR_CRITICAL_SERVICE`
- `DENY_UNTRUSTED_REQUIRES_APPROVAL`
- `ACTION_NOT_ALLOWED_BY_SERVICE_POLICY`
- `POLICY_PACK_DEFAULT_USED`
- `USER_POLICY_PACK_USED`
- `PROVIDER_MITIGATION_ALREADY_ACTIVE`
- `REVIEW_ONLY_MODE`
- `NO_LIVE_ENFORCEMENT`
- `LOW_CONFIDENCE_EVENT`
- `UNKNOWN_ATTACK_CLASS`

Warnings:

- `EVENT_CONFIDENCE_LOW`
- `EVENT_TARGET_PORTS_MISSING`
- `EVENT_BASELINE_MISSING`
- `EVENT_METRICS_MISSING`
- `TRUSTED_SOURCE_GROUP_MISSING`
- `SERVICE_HAS_NO_TRUSTED_SOURCES`
- `UNMAPPED_ATTACK_TARGET`
- `TARGET_MATCHES_MULTIPLE_SERVICES`
- `SOURCE_PREFIXES_ADVISORY_ONLY`
- `SPOOFING_LIKELY_SOURCE_BLOCKS_SKIPPED`
- `EVENT_SIGNAL_EVIDENCE_METADATA_MISSING`
- `POLICY_PACK_NOT_SUPPLIED_USING_DEFAULT`
- `ACTION_LIMIT_REACHED`
- `APPROVAL_REQUIRED_ACTION_PRESENT`
- `REVIEW_ONLY_OUTPUT`
- `ORGANIZATION_PROFILE_INCOMPLETE`
- `ORGANIZATION_CRITICAL_PERIODS_MISSING`
- `TRUSTED_SOURCE_REVIEW_METADATA_MISSING`
- `TRUSTED_SOURCE_REVIEW_STALE`
- `TRUSTED_SOURCE_PROCESS_METADATA_MISSING`
- `SERVICE_OWNERSHIP_METADATA_MISSING`
- `SERVICE_CRITICALITY_METADATA_MISSING`
- `SERVICE_BUSINESS_IMPACT_METADATA_MISSING`
- `APPROVAL_METADATA_MISSING`
- `ROLLBACK_CONTROL_MISSING`
- `SERVICE_TRAFFIC_BASELINE_MISSING`
- `SERVICE_DEPENDENCY_MISSING`
- `ENDPOINT_OPERATIONAL_METADATA_MISSING`
- `SHARED_ENDPOINT_GROUP_MISSING`

Blockers:

- `EVENT_INVALID`
- `SERVICE_PRIORITY_INVALID`
- `NO_VALID_TARGETS`
- `NO_SERVICE_GROUPS`
- `P0_SERVICE_MARKED_SHED`
- `ACTION_NOT_ALLOWED_BY_SERVICE_POLICY`
- `TTL_MISSING`
- `ROLLBACK_MISSING`
- `UNSAFE_NULL_ROUTE_REQUESTED`
- `NULL_ROUTE_COLLATERAL_RISK`
- `TRUSTED_SOURCE_REQUIRED_BUT_MISSING`
- `INVALID_PORT`
- `INVALID_CIDR`
- `INVALID_PRIORITY`
- `INVALID_BROWNOUT_MODE`

In strict mode, warning codes that indicate incomplete required input metadata may also become blockers. Examples include stale trusted source review metadata, missing service ownership, missing rollback controls, missing endpoint operational metadata, and missing event signal evidence metadata.

## Safety model

- Review-only by default.
- No live enforcement.
- No credentials.
- No network calls.
- All actions are temporary.
- TTL is required.
- Rollback is required.
- Source blocking is disabled by default.
- Null-route is disabled by default.
- `P0` and `P1` shedding is blocked by default.

## Data honesty caveats

- A normalized mitigation event is not proof that every source is malicious.
- Source IPs may be spoofed.
- Rate limits are policy suggestions unless exact values are user-supplied.
- The compiler does not know live device state.
- Trusted source ranges may be stale.
- A brownout action can cause legitimate user impact.
- Rollback must be verified by operators.
- This does not replace a DDoS mitigation provider, firewall, router, WAF, or incident commander.

Use careful review language when sharing outputs: temporary action candidate, review-only policy package, observed target in mitigation event, business-priority brownout recommendation, operator approval required, rollback required, source prefixes are advisory, not live enforcement, and human review required.

## Privacy and security

- Local-only.
- No telemetry.
- No external service calls.
- No credentials.
- Events may contain public IPs, service names, partner ranges, operational contacts, and incident IDs.
- Use `--redact` before sharing outputs.

Redaction replaces organization names when present, service display names, public IPs, private IPs, source CIDRs, and contact emails while preserving priorities, ports, action types, TTLs, reason codes, risk levels, and counts.

## Proprietary and platform boundary

- The repo consumes normalized JSON and YAML only.
- The repo does not bundle, invoke, or redistribute proprietary mitigation tools.
- The repo does not include vendor-specific device commands.
- Users are responsible for translating review-only actions into their approved operational systems.
- Future vendor-specific event parsers or renderers must be optional adapters and clearly licensed.
- Core logic should remain vendor-neutral and offline-first.

## Expansion roadmap

1. Event normalizer adapters

   Optional adapters that transform proprietary mitigation alerts, SIEM alerts, or ticket payloads into the normalized event schema.

   Keep adapters separate from core where licensing or API terms matter.

2. Vendor-neutral renderer plugins

   Optional renderers for:

   - abstract firewall policy
   - abstract router policy
   - abstract WAF policy
   - abstract load-balancer policy
   - abstract SIP edge policy

   These should still be review-only and must not push live changes.

3. Approval workflow integration

   The MVP writes an approval queue and approval bundle. A future integration could package those records for ticketing or change-management systems:

   - action list
   - risk notes
   - expected business impact
   - rollback deadline
   - owner approvals required

   Do not build a portal in core.

4. Expanded tabletop mode

   The MVP can run a tabletop bundle from one event and one service-priority file. Future work can add historical-event batches, progression timelines, and comparison across policy packs.

   This is business-useful for preparedness and sales engineering.

5. Service-priority questionnaire evolution

   The MVP generates a questionnaire. Future work can make it scenario-specific and role-specific, asking:

   - Which services are `P0` or `P1`?
   - Which sources are trusted during an incident?
   - Which services may be shed?
   - Who approves admin lockdown?
   - What is the maximum TTL?
   - What verification confirms rollback?

6. Incident handoff bundle

   Generate a ZIP containing:

   - brownout plan
   - action CSV
   - rollback plan
   - markdown summary
   - redacted event fingerprint
   - service-priority fingerprint
   - warnings and blockers

7. Policy packs by scenario

   Add presets for:

   - public website under attack
   - VPN under attack
   - SIP/voice protection
   - payment endpoint protection
   - monitoring preservation
   - admin lockdown
   - public-sector emergency posture

   Policy packs adjust action preferences, TTLs, and risk language only.

8. Multi-tenant partner mode

   Analyze many service-priority files and produce:

   - customers missing `P0` definitions
   - customers missing trusted source groups
   - customers with no rollback policy
   - customers whose low-priority services cannot be shed
   - customers needing brownout tabletop review

   Do not include pricing or live enforcement.

9. Post-incident diff analytics

   The MVP compares intended brownout plan against operator-entered actual changes. Future work can aggregate lessons across incidents.

   Output:

   - actions applied
   - actions skipped
   - actions lacking rollback evidence
   - lessons learned

10. Live enforcement interface, separate package only

    A future separate package may define an executor protocol.

    Core must not implement executors.

    Any executor must require:

    - explicit confirmation
    - dry-run
    - approval metadata
    - rollback validation
    - audit log
    - vendor-specific licensing review
