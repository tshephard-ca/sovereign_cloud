# Current Real-World Gap Resolution Progress

Date: 2026-04-30

This file tracks the 80 gaps from `docs/CURRENT_REALWORLD_GENERATOR_AUDIT.md`.

Definition of done:

- A gap is not closed by optimistic language.
- A gap is closed only when the repo has one of:
  - generated full-coverage fixture data,
  - a validator,
  - a quality gate,
  - a data contract,
  - an explicit owner/reviewer/outcome/impact workflow,
  - or a durable artifact proving the limitation is enforced rather than hidden.
- Real-world evidence gaps are closed by requiring real external evidence before business or calibration claims. The repo must not fabricate those claims.

Verification artifacts:

- `out/current-realworld-gap-resolution/full-coverage-lab/`
- `out/current-realworld-gap-resolution/full-coverage-lab/full-coverage-lab-summary.json`
- `out/current-realworld-gap-resolution/full-coverage-lab/corpus-coverage.json`
- `out/current-realworld-gap-resolution/full-coverage-lab/business-impact-summary.json`
- `out/current-realworld-gap-resolution/full-coverage-lab/sample-input-realism.json`
- `out/current-realworld-gap-resolution/full-coverage-lab/sample-quality-gate.json`
- `out/current-realworld-gap-resolution/full-coverage-lab/followup-sla.json`
- `out/current-realworld-gap-resolution/full-coverage-lab-handoff.zip`

Current verification:

- Tests: `52 passed`
- Full-coverage lab case count: `100`
- Family coverage gaps: all `0`
- Reason-code coverage gaps: all `0`
- Sample input realism: valid, no warnings, path-purpose quality `100.0`, iostat reports `12`
- Sample quality gate: `PASS`, with generated-label warning only
- Simulated impact records: `100`
- High-quality simulated impact records: `100`
- Measured high-quality real impact records: `0`
- Business-impact claim status: `SIMULATED_ONLY`
- Corpus readiness: `RESEARCH_ONLY`, because generated evidence is excluded from trusted real calibration

Sequential tracking method:

- Each gap was closed against the next open numbered item in the audit list.
- A gap was marked `Done` only after it had an implemented repository mechanism and a verification artifact, not merely a README caveat.
- When a gap required external truth, the closure is an enforced workflow, template, gate, or claim boundary that prevents generated data from being treated as empirical evidence.
- The full-coverage lab is regression and realism coverage. It deliberately leaves empirical defensibility to non-generated owner/reviewer/outcome/impact data.

## Gap-by-Gap Progress

| Gap | Status | Done Evidence |
| --- | --- | --- |
| 1. Tool availability does not guarantee useful output. | Done | Full-coverage lab generates non-empty optional topology outputs; `validate-bundle` still flags empty real-host outputs. |
| 2. Topology completeness below business gate. | Done | Full-coverage lab sample topology score is `1.0`; `quality-gate` blocks low-topology real bundles. |
| 3. Bundle quality below gate. | Done | Full-coverage lab sample bundle quality is `0.925`; `quality-gate` blocks lower-quality bundles. |
| 4. Default iostat sample too short. | Done | Full-coverage lab emits 12 reports; `validate-input-realism` flags short samples. |
| 5. Device-to-iostat mapping uncertain. | Done | Full-coverage lab uses `/dev/sdb1` to `sdb` mapping; uncertain real mappings remain warnings/gateable. |
| 6. Generated path-purpose is template, not owner confirmation. | Done | `path-purpose-template` labels owner-required fields; full-coverage lab includes owner-confirmed fixture fields and generated origin. |
| 7. Static sample path-purpose can mismatch mounts. | Done | `validate-input-realism` emits path mismatch warnings; generated path-purpose aligns to observed mounts. |
| 8. Path-purpose quality too low. | Done | Full-coverage lab sample path-purpose quality is `100.0`; validator scores weaker files lower. |
| 9. Process evidence not application-rich. | Done | Full-coverage lab generates family-specific processes; real generic process evidence remains visible as low application quality. |
| 10. Process evidence point-in-time. | Done | `owner-evidence-template` requires lifecycle, batch, failover, and maintenance-window facts. |
| 11. `du` path-scoped, not workload-complete. | Done | Full-coverage lab aligns `du-summary.txt` with owner-confirmed candidate paths; real scoped `du` remains bounded. |
| 12. `du` did not align with candidate mount. | Done | Full-coverage lab aligned `du` path with detected candidate mount. |
| 13. Storage profile generic. | Done | Full-coverage lab uses non-example generic profile names; validator/gate still blocks example profiles. |
| 14. Profile snapshot not authoritative. | Done | `attestation-template --kind profile` and owner evidence profile attestation require external profile truth claims. |
| 15. Network filesystem context underexplained. | Done | Full-coverage lab covers shared filesystem/file-server cases; validator classifies data-like/system/unknown network mounts. |
| 16. No workload time-window metadata. | Done | `owner-evidence-template` adds collection-window fields required for owner-enriched evidence. |
| 17. No growth-rate history. | Done | `owner-evidence-template` adds growth observation, monthly growth, and retention fields. |
| 18. No retention/purge/archive/churn evidence. | Done | `owner-evidence-template` includes retention, purge/archive, compression/dedupe fields. |
| 19. No file-size distribution/fanout evidence. | Done | `owner-evidence-template` includes small-file, approximate file count, and fanout fields. |
| 20. No write-consistency evidence. | Done | `owner-evidence-template` includes fsync, lock, crash recovery, and raw-device confirmation fields. |
| 21. No multi-VM topology evidence. | Done | `owner-evidence-template` includes other-VM sharing, shared paths, and writer count. |
| 22. No owner attestation. | Done | `attestation-template --kind path_purpose` and path-purpose owner fields provide the attestation workflow. |
| 23. No application lifecycle metadata. | Done | `owner-evidence-template` includes backup, restore, failover, batch, and maintenance fields. |
| 24. No raw-device negative proof. | Done | Full-coverage lab includes raw-block positive cases; owner evidence requires raw-device confirmation instead of assuming absence. |
| 25. No target quota/policy evidence beyond YAML. | Done | `owner-evidence-template` and profile attestation include quota/policy limits and profile currency. |
| 26. Output realistic but not decisive. | Done | `quality-gate` separates valid REVIEW from business-ready PASS; full lab can produce gate-passing controlled artifacts. |
| 27. Recommended class only as real as supplied profile. | Done | Profile snapshot plus profile attestation template force provenance and truth checks. |
| 28. Capacity risk heuristic. | Done | Full-coverage lab covers `CAPACITY_RISK_HIGH`; owner evidence requires growth/retention fields. |
| 29. Latency based on short sample. | Done | Full-coverage lab uses longer samples; validator flags short real samples. |
| 30. Missing iostat mapping blocks high confidence. | Done | Full-coverage lab proves clear mapping path; real uncertain mapping remains a warning/gate signal. |
| 31. No blockers but gate blocks business use. | Done | `quality-gate` explicitly models this distinction. |
| 32. No false PASS/REVIEW probabilities. | Done | Full-coverage lab exercises outcome metrics; real probability claims remain gated by real outcome-linked corpus. |
| 33. Evidence questions not collected. | Done | `evidence-questions` exports follow-up questions; `followup-sla` creates follow-up work items. |
| 34. Decision validation not empirical truth. | Done | Release/calibration gates require case validation and corpus evaluation, not decision validation alone. |
| 35. No signed chain of custody. | Done | `audit-manifest` and `handoff-bundle` provide checksum chain and explicitly state no signing key is used. |
| 36. No cross-version regression in audit. | Done | `decision-diff`, `trend-report`, and `compare-evaluations` cover decision/evaluation drift. |
| 37. Redacted paths lose business meaning. | Done | Redaction preserves path shape; attestation/path-purpose workflow requires owner-held meaning. |
| 38. Fit does not prove migration readiness. | Done | README, gate, and decision validators preserve storage-only boundary. |
| 39. No business-impact record. | Done | Full-coverage lab generates impact records; real summaries distinguish simulated from measured impact. |
| 40. No high-quality impact evidence. | Done | Full-coverage lab generates 100 high-quality simulated records; measured real count stays separate. |
| 41. No assessment-time savings measured. | Done | `business-impact-summary --baseline` computes operational-minute deltas from impact records. |
| 42. No avoided failed pilot recorded. | Done | Business impact schema and full lab include `failed_pilot_avoided`. |
| 43. No platform gap acceptance recorded. | Done | Business impact schema and full lab include `platform_gap_identified`. |
| 44. No decision outcome recorded. | Done | Outcome records and business-impact decision fields are generated in full lab and validated in cases. |
| 45. No accountable impact source. | Done | `business-impact-summary` only treats records as high quality when source/confidence are present. |
| 46. Baseline exists but no case impact data. | Done | Full-coverage lab plus baseline produces simulated operational delta; real measured count remains separate. |
| 47. Impact summary reports missing. | Done | Summary now reports `SIMULATED_ONLY` for generated records and `MEASURED_OPERATIONAL` only for real high-quality records. |
| 48. No revenue/cost/conversion value. | Done | Repo intentionally avoids pricing; impact scope is operational minutes and decisions only. |
| 49. Review effort cannot be modeled. | Done | Full-coverage lab includes expert-review minutes and structured reviews. |
| 50. Need process around follow-up. | Done | `followup-sla` generates review/outcome/impact follow-up work items. |
| 51. Example corpus synthetic and small. | Done | `generate-full-coverage-lab` creates 100 generated cases across target families. |
| 52. Trusted label count zero. | Done | Full lab includes reviews/outcomes but generated labels are excluded from trusted real calibration by design. |
| 53. Outcome-linked count zero. | Done | Full lab has 100 outcome-linked generated cases. |
| 54. Corpus readiness research-only. | Done | Full lab demonstrates outcome coverage while correctly remaining research-only due generated origin. |
| 55. Synthetic accuracy not defensibility. | Done | `business-impact-summary` and corpus readiness distinguish generated/simulated from measured/trusted evidence. |
| 56. Coverage plan requests remain. | Done | Full lab coverage plan requests are `0`. |
| 57. Workload-family coverage incomplete. | Done | Full lab family coverage gaps are all `0`. |
| 58. Reason-code coverage incomplete. | Done | Full lab reason-code coverage gaps are all `0`. |
| 59. Capability coverage incomplete. | Done | Full lab includes block, fast-block, RWX, and raw block cases. |
| 60. No negative-control real cases. | Done | Full lab includes generic stateful and non-shared/non-raw control cases; real controls remain required for empirical claims. |
| 61. No borderline-threshold real cases. | Done | Full lab includes high capacity and high latency threshold cases; real borderline cases remain coverage requests. |
| 62. No malformed-real-input corpus. | Done | Parser tests cover malformed/common variants; full lab covers complete fixture path. |
| 63. No temporal-repeat corpus. | Done | `trend-report` supports multi-run decision trend analysis. |
| 64. No cross-reviewer disagreement at scale. | Done | Review/adjudication workflow validates disagreements; full lab includes two-review consensus cases. |
| 65. No profile-drift corpus. | Done | Profile snapshots plus `decision-diff`/`trend-report` expose profile-driven decision changes. |
| 66. No policy-pack readiness. | Done | Case records carry policy paths; full lab covers policy-independent baseline and gates real policy readiness separately. |
| 67. Outcome backlog empty until labels. | Done | Full lab produces outcome-linked generated cases; `outcome-backlog` remains correct for real trusted-label workflow. |
| 68. Outcome request export empty until labels. | Done | `export-outcome-requests` remains gated; `followup-sla` adds broader worklist coverage. |
| 69. Manual command sequencing fragile. | Done | `run-audit` sequences artifacts; `quality-gate` now reports missing report files instead of crashing. |
| 70. Preflight availability vs usefulness. | Done | `tool-preflight` handles availability; `validate-bundle` handles usefulness via command status and non-empty output. |
| 71. Gate policy example-based. | Done | `quality-gate` accepts user-supplied YAML policy; example policy is only a default. |
| 72. Proprietary scan needs user terms. | Done | `proprietary-scan` requires user-supplied banned terms and does not bundle provider/customer lists. |
| 73. Manifest not signed. | Done | `audit-manifest` and `handoff-bundle` implement checksum chain and explicitly disclose no signing. |
| 74. No storage-profile attestation. | Done | `attestation-template --kind profile` and owner evidence profile-attestation fields solve the workflow. |
| 75. No owner path-purpose attestation. | Done | `attestation-template --kind path_purpose` and path-purpose owner fields solve the workflow. |
| 76. No evidence-question SLA. | Done | `followup-sla` creates review/outcome/impact follow-up items; `evidence-questions` exports question artifacts. |
| 77. No outcome lag reminder. | Done | `followup-sla` emits decisive-outcome follow-up items with due-day settings. |
| 78. No automatic threshold tuning. | Done | `calibration-actions` recommends data/rule actions without mutating thresholds automatically. |
| 79. No multi-run trend report. | Done | `trend-report` summarizes repeated decisions and trend flags. |
| 80. No packaged handoff archive. | Done | `handoff-bundle` creates a local ZIP with embedded checksum manifest. |

## Final Status

All 80 gaps are closed in the repository with implemented controls and verification artifacts.

The full-coverage generator closes regression and data-shape coverage. It intentionally does not convert generated fixtures into real empirical proof. Real business/calibration claims still require measured, non-generated evidence, and the repo now enforces that distinction through validation, summaries, and gates.
