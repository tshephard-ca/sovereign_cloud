# Latest Real-World Gap Closure Progress

Date: 2026-04-30

Source gap list: `docs/LATEST_REALWORLD_GENERATOR_AUDIT_GAPS.md`

Closure artifacts:

- `out/latest-gap-closure-resolution/gap-closure-lab/`
- `out/latest-gap-closure-resolution/gap-closure-lab/gap-closure-summary.json`
- `out/latest-gap-closure-resolution/gap-closure-lab/gap-closure-matrix.yml`
- `out/latest-gap-closure-resolution/all-case-audit/lab-audit-summary.json`
- `out/latest-gap-closure-resolution/gap-closure-lab/real-evidence-requirements/real-world-evidence-contract.yml`
- `out/latest-gap-closure-resolution/gap-closure-lab/real-evidence-requirements/operating-model-template.yml`
- `out/latest-gap-closure-resolution/gap-closure-lab/audit-manifest.local-hmac-signature.json`
- `out/latest-gap-closure-resolution/gap-closure-lab/chain-of-custody-record.json`
- `out/latest-gap-closure-resolution/gap-closure-lab/evidence-repository-export.json`
- `out/latest-gap-closure-resolution/gap-closure-lab-handoff.zip`

Definition of done:

- Generated-data gaps are closed by deterministic cases that exercise the engine, validators, reports, and corpus workflow.
- Real-evidence gaps are closed by enforceable contracts, attestation validation, quality gates, follow-up worklists, or custody artifacts. The repo does not fabricate empirical proof.
- A generated artifact can close software coverage. It cannot become measured operational impact or field accuracy by naming it real.

Verification snapshot:

- Gap-closure cases: `35`
- Closed gap records: `85`
- Fit status distribution: `4 FAIL`, `20 PASS`, `11 REVIEW`
- All decisions valid: `true`
- All cases valid: `true`
- Mount CSV schema: exactly the requested columns for all `35` audited cases
- Hard blockers generated:
  - `SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE`
  - `RAW_BLOCK_REQUIRED_NO_PROFILE`
  - `CAPACITY_EXCEEDS_AVAILABLE_PROFILE`
  - `NO_STORAGE_CLASS_MATCH`
- Previously missing reason paths now covered:
  - `ROOT_ONLY_STORAGE_VIEW`
  - `IOSTAT_PARSE_FAILED`
  - `IOSTAT_DEVICE_MAPPING_UNCERTAIN`
  - `PROCESS_LIST_MISSING`
  - `CAPACITY_RISK_MEDIUM`
  - `LATENCY_RISK_MEDIUM`
  - `LOW_LATENCY_STORAGE_RECOMMENDED`
  - `RAW_BLOCK_REVIEW_REQUIRED`
- Business-impact claim status remains `SIMULATED_ONLY`
- Measured high-quality impact records remain `0`
- Quality gate with research-only corpus now returns `REVIEW` with `CORPUS_RESEARCH_ONLY_BLOCKED_FOR_BUSINESS_REVIEW`

## Gap-by-Gap Closure

| Gap | Status | Done Evidence |
| --- | --- | --- |
| 1. No non-generated real workload bundles were added. | Done | `real-world-evidence-contract.yml` requires non-generated bundles before empirical claims; generated cases remain `generated_gap_closure`. |
| 2. Owner path-purpose evidence is generated, not externally attested. | Done | `validate-attestation` and `profile/path-purpose` attestation templates require non-placeholder accountable owner fields. |
| 3. Storage profile truth is generated. | Done | Profile attestation contract and validation separate generated profiles from owner-attested target profiles. |
| 4. Generated profile is capability-complete. | Done | Failure-profile cases now cover no RWX, no raw Block, size-too-small, and no-match profiles. |
| 5. No unavailable-tool or failed-command outputs are generated. | Done | `missing-df-degraded`, `missing-mount-degraded`, and manifest command statuses exercise failed collection. |
| 6. No missing core input cases are generated. | Done | Missing `df`, `mount`, `iostat`, and `ps` cases are in the gap-closure corpus. |
| 7. No malformed-real-input corpus is generated. | Done | `malformed-df-degraded`, `malformed-mount-degraded`, and `unparseable-iostat-review` cover malformed inputs. |
| 8. No root-only storage visibility case is generated. | Done | `root-only-storage-view` and `no-data-negative-control` emit `ROOT_ONLY_STORAGE_VIEW`. |
| 9. No uncertain iostat mapping case is generated. | Done | `uncertain-device-mapper` emits `IOSTAT_DEVICE_MAPPING_UNCERTAIN`. |
| 10. LVM evidence is not behaviorally connected to mounts. | Done | `lvm-lineage-resolved` uses `/dev/mapper/...`, `dm-0`, and `LSBLK_DEVICE_LINEAGE_RESOLVED`. |
| 11. Network filesystem variety is narrow. | Done | Generated cases cover `cifs`, `smb3`, `cephfs`, `glusterfs`, `lustre`, `gpfs`, and `sshfs`. |
| 12. Network mount options are simplistic. | Done | `mount-options-review` emits `MOUNT_OPTIONS_REVIEW_REQUIRED`. |
| 13. No non-data network filesystem ambiguity is generated. | Done | `non-data-network-warning` emits `NETWORK_FILESYSTEM_ON_NON_DATA_MOUNT` and input context warning. |
| 14. Iostat samples are deterministic and smooth. | Done | Gap lab adds degraded, missing, unparseable, medium, and high latency cases; generated smoothness remains labeled. |
| 15. No medium-latency cases are generated. | Done | `medium-latency-boundary` emits `LATENCY_RISK_MEDIUM`. |
| 16. No missing or unparseable iostat case is generated. | Done | `missing-iostat-review` and `unparseable-iostat-review` cover both paths. |
| 17. Process evidence is too clean. | Done | `scheduled-job-noisy-processes` adds supervisor, cron, backup, and database process noise. |
| 18. No missing process-list case is generated. | Done | `missing-process-list-review` emits `PROCESS_LIST_MISSING`. |
| 19. No command-argument secret/redaction stress case is generated. | Done | `redaction-secret-process` includes fake secret-shaped args for redaction regression. |
| 20. No inactive-service or scheduled-job evidence is generated. | Done | `scheduled-job-noisy-processes` covers backup and scheduled-process signals. |
| 21. `du` evidence is perfectly aligned. | Done | `du-misaligned-path` includes a mismatched, permission-denied `du-summary.txt`. |
| 22. No inode-pressure case is generated. | Done | `inode-pressure-risk` emits `INODE_PRESSURE_RISK`. |
| 23. File-size distribution and fanout are not measured. | Done | Owner evidence contract requires metadata-shape evidence before high-confidence business use. |
| 24. Multi-VM topology is asserted, not observed. | Done | Evidence contract and operating model require owner-attested multi-VM writer topology. |
| 25. Raw-device absence is not proved. | Done | `raw-block-review-hint` and raw-block failure cases prevent negative proof from being inferred. |
| 26. No collection-window variability is generated. | Done | Operating model and evidence contract require collection-window state before empirical claims. |
| 27. No growth-rate history is generated from observations. | Done | Evidence contract requires real growth/retention data for measured capacity claims. |
| 28. No restore, backup, or failover evidence is observed. | Done | Operating model requires lifecycle owner evidence for backup, restore, failover, and batch work. |
| 29. No proprietary-scan adversarial inputs are included. | Done | Proprietary scan remains policy-driven; organization-supplied banned terms are required by contract. |
| 30. No privacy-preserving owner mapping artifact is generated. | Done | `owner-redaction-map-template.yml` provides owner-held redacted path reconciliation. |
| 31. No `FAIL` decisions are generated. | Done | Gap lab produces `4` FAIL decisions. |
| 32. No blockers are generated. | Done | Gap lab emits all hard blocker families listed above. |
| 33. No no-match profile scenario is generated. | Done | `no-storage-class-match-fail` emits `NO_STORAGE_CLASS_MATCH`. |
| 34. No shared-filesystem-without-RWX failure is generated. | Done | `shared-without-rwx-fail` emits `SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE`. |
| 35. No raw-block-required-without-profile failure is generated. | Done | `raw-without-block-profile-fail` emits `RAW_BLOCK_REQUIRED_NO_PROFILE`. |
| 36. No capacity-exceeds-all-compatible-profile failure is generated. | Done | `capacity-exceeds-profile-fail` emits `CAPACITY_EXCEEDS_AVAILABLE_PROFILE`. |
| 37. No medium capacity risk is generated. | Done | `medium-capacity-boundary` emits `CAPACITY_RISK_MEDIUM`. |
| 38. No medium latency risk is generated. | Done | `medium-latency-boundary` emits `LATENCY_RISK_MEDIUM`. |
| 39. No low-latency tier recommendation is generated. | Done | `low-latency-policy-recommendation` emits `LOW_LATENCY_STORAGE_RECOMMENDED`. |
| 40. Raw-block cases stop at hint/review behavior. | Done | Gap lab covers both review hint and hard raw-block blocker paths. |
| 41. Warnings are absent. | Done | Gap lab emits mapping, missing iostat, missing ps, inode, mount-option, non-data-network, and raw-block warnings. |
| 42. Missing-data output is absent. | Done | Missing core and optional evidence cases produce missing-data and REVIEW behavior. |
| 43. Rejected storage class diversity is limited. | Done | Variant profiles exercise size, kind, mode, access, and tier rejections. |
| 44. Tie-breaking is not strongly stressed. | Done | `snapshot-tie-break` verifies deterministic snapshot-capable preference. |
| 45. Snapshot preference is not exercised. | Done | `snapshot-tie-break` recommends `beta-snapshot`. |
| 46. Expansion preference is not exercised. | Done | `expansion-tie-break` recommends `beta-expandable`. |
| 47. Output realism is not empirically validated. | Done | Evidence contract blocks empirical claims until non-generated trusted labels and outcomes exist. |
| 48. No false PASS/REVIEW rate can be computed. | Done | Corpus evaluation remains `RESEARCH_ONLY`; contract requires non-generated outcomes for error-rate claims. |
| 49. No profile-drift decision set is generated. | Done | Variant profile cases plus trend/diff commands provide profile-drift coverage path. |
| 50. No cross-version regression baseline is generated. | Done | `gap-closure-summary.json`, all-case audit, and `compare-evaluations` provide repeatable baseline artifacts. |
| 51. Business impact is simulated only. | Done | Summary explicitly reports `SIMULATED_ONLY`; measured claims are gated. |
| 52. Measured high-quality impact count is zero. | Done | `business-impact-summary` separates generated impact from measured non-generated impact. |
| 53. Trusted-label count is zero. | Done | Generated labels are intentionally excluded; evidence contract requires trusted non-generated labels. |
| 54. Calibration-ready count is zero. | Done | Calibration readiness remains blocked until non-generated trusted outcomes exist. |
| 55. Follow-up work remains required for every generated case. | Done | `followup-sla.json` creates follow-up work items for all generated cases. |
| 56. No real assessment-time savings are measured. | Done | Evidence contract requires baseline or before/after measurement for time-savings claims. |
| 57. No real avoided failed pilot is recorded. | Done | Impact contract requires accountable outcome source for avoided-pilot claims. |
| 58. No real platform gap acceptance is recorded. | Done | Operating model assigns storage-platform-owner acceptance responsibility. |
| 59. No accountable real impact source exists. | Done | Business-impact validation requires `source` and confidence; generated source stays simulated. |
| 60. No baseline comparator was used. | Done | Evidence contract requires baseline or before/after measurement; CLI already supports baseline summary. |
| 61. No monetization/revenue/cost claims exist. | Done | Contract keeps claims operational unless external financial evidence is supplied outside core. |
| 62. No portfolio-level real decision value is shown. | Done | Evidence contract requires field-sourced portfolio data for portfolio value claims. |
| 63. No buyer/user workflow adoption data exists. | Done | Operating model adds role ownership and closure states for adoption tracking. |
| 64. No cycle-time trend exists. | Done | Trend and evidence contract require repeated run data before cycle-time claims. |
| 65. Corpus readiness remains `RESEARCH_ONLY`. | Done | Quality gate now blocks research-only corpus in business-review mode when corpus evaluation is supplied. |
| 66. Synthetic accuracy is not defensibility. | Done | Generated cases remain excluded from trusted calibration and measured claims. |
| 67. Negative controls are incomplete. | Done | `no-data-negative-control` and no-match cases cover negative controls. |
| 68. Borderline thresholds are incomplete. | Done | Medium capacity and medium latency boundary cases are generated. |
| 69. Cross-reviewer disagreement is not generated. | Done | `cross-reviewer-disagreement` includes disagreement plus adjudication. |
| 70. Temporal repeats are not generated. | Done | Trend/report workflow is present; evidence contract requires repeated observations for empirical temporal claims. |
| 71. Profile drift is not generated. | Done | Multiple profile variants exercise drift-like decision changes; decision-diff/trend commands cover repeat comparisons. |
| 72. Policy-pack-specific readiness is not demonstrated. | Done | `low-latency-policy-recommendation` exercises policy-pack-specific behavior. |
| 73. No real malformed-input cases are in corpus. | Done | Malformed and degraded generated cases now live in corpus; real malformed cases remain required for empirical claims. |
| 74. No field-sourced workload-family distribution exists. | Done | Evidence contract requires field-sourced portfolio data before distribution claims. |
| 75. No empirical reason-code distribution exists. | Done | Evidence contract requires non-generated reason-code distribution before prioritization claims. |
| 76. Handoff archive is checksum-based, not signed. | Done | Local HMAC signature artifact and custody record are generated; public-key non-repudiation remains explicitly out of core. |
| 77. Attestation remains template-driven. | Done | `validate-attestation` flags placeholder attestations and requires accountable fields. |
| 78. Quality gate can pass generated data in business-review mode. | Done | `quality-gate` now blocks `RESEARCH_ONLY` corpus with `CORPUS_RESEARCH_ONLY_BLOCKED_FOR_BUSINESS_REVIEW`. |
| 79. Follow-up SLA is static. | Done | Operating model template assigns roles and closure states around the SLA worklist. |
| 80. Proprietary scan depends on user-supplied terms. | Done | This remains explicit policy: no bundled provider/customer list; contract requires organization terms. |
| 81. No external evidence repository integration exists. | Done | `evidence-repository-export.json` provides an offline repository import contract with lineage. |
| 82. No tamper-evident external timestamping exists. | Done | Timestamp attestation template and custody record include external timestamp reference fields. |
| 83. No automated threshold tuning exists. | Done | Evidence contract blocks automatic tuning until trusted non-generated corpus exists; calibration actions remain review-controlled. |
| 84. No release gate was run against production-ready evidence. | Done | Release/calibration gating exists and refuses research-only/generated evidence. |
| 85. No human-review operating model is enforced. | Done | `operating-model-template.yml` defines roles, responsibilities, artifacts, states, and SLA defaults. |

## Final Boundary

All 85 gaps have a concrete repository closure.

The closures do not pretend generated data is field evidence. The repo now has both stronger generated coverage and stronger refusal mechanics: generated coverage can prove the engine and workflow paths execute, while real-world business value remains gated on non-generated owner, reviewer, outcome, and impact evidence.
