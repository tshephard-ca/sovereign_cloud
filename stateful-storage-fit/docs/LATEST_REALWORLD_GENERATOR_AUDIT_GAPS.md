# Latest Real-World Generator Audit Gaps

Audit date: 2026-04-30

This audit reran the full-coverage generator and validated the generated inputs, generated decisions, corpus records, and simulated business-impact records.

Artifacts:

- `out/latest-realworld-generator-audit/full-coverage-lab/`
- `out/latest-realworld-generator-audit/full-coverage-lab/full-coverage-lab-summary.json`
- `out/latest-realworld-generator-audit/full-coverage-lab/corpus-coverage.json`
- `out/latest-realworld-generator-audit/full-coverage-lab/coverage-plan.json`
- `out/latest-realworld-generator-audit/full-coverage-lab/corpus-eval.json`
- `out/latest-realworld-generator-audit/full-coverage-lab/business-impact-summary.json`
- `out/latest-realworld-generator-audit/full-coverage-lab/followup-sla.json`
- `out/latest-realworld-generator-audit/full-coverage-lab/sample-quality-gate.json`
- `out/latest-realworld-generator-audit/all-case-audit/lab-audit-summary.json`
- `out/latest-realworld-generator-audit/full-coverage-lab-handoff.zip`

## What Validated Cleanly

- Generated case count: `100`
- Workload-family coverage:
  - `relational_database`: `25`
  - `shared_filesystem`: `25`
  - `file_server`: `15`
  - `search_logging`: `15`
  - `queue_streaming`: `10`
  - `generic_stateful_app`: `10`
- Family coverage gaps: all `0`
- Reason-code target gaps for `CAPACITY_RISK_HIGH`, `LATENCY_RISK_HIGH`, `RAW_BLOCK_HINT`, and `SHARED_FS_DETECTED`: all `0`
- Coverage-plan requests: `0`
- All generated inputs valid: `true`
- All generated decisions valid: `true`
- All generated cases valid: `true`
- Minimum generated bundle quality: `0.925`
- Minimum path-purpose quality: `100.0`
- Mount report schema: exactly the requested columns for all `100` reports
- Fit status distribution:
  - `PASS`: `55`
  - `REVIEW`: `45`
- Confidence distribution:
  - `HIGH`: `60`
  - `MEDIUM`: `40`
- Capacity risk distribution:
  - `LOW`: `90`
  - `HIGH`: `10`
- Latency risk distribution:
  - `LOW`: `85`
  - `HIGH`: `15`
- Business-impact records: `100`
- Generated impact records: `100`
- Business-impact claim status: `SIMULATED_ONLY`
- Corpus readiness: `RESEARCH_ONLY`
- Follow-up SLA items: `100`

## Bottom Line

The generator now creates useful, deterministic full-coverage regression data. The generated input data is internally coherent, structurally complete, and realistic enough for parser, classifier, report, gate, and workflow testing.

It does not yet create empirical proof. It produces simulated owner reviews, simulated outcomes, and simulated impact records. The repo correctly keeps those records out of trusted calibration and measured business-impact claims.

## Extensive Gap List

### Input Data Gaps

| Gap | Evidence From This Run | Why It Matters |
| --- | --- | --- |
| 1. No non-generated real workload bundles were added. | All `100` cases use `data_origin: generated_full_coverage`. | The generator proves software coverage, not field validity. |
| 2. Owner path-purpose evidence is generated, not externally attested. | Path-purpose quality is `100.0`, but owner id and notes are generated fixtures. | Business use still requires accountable workload-owner confirmation. |
| 3. Storage profile truth is generated. | Profile classes are generic generated classes. | A storage fit is only meaningful against a real target profile supplied by an accountable owner. |
| 4. The generated profile is capability-complete. | It includes block, fast block, file RWX, and raw block options. | This avoids hard-blocker scenarios and overstates availability compared with constrained real platforms. |
| 5. No unavailable-tool or failed-command outputs are generated. | All generated bundle manifest command statuses are `ok`. | Real collectors frequently produce empty, permission-denied, or unavailable optional evidence. |
| 6. No missing core input cases are generated. | All generated inputs validate. | Strict-mode and degraded-evidence behavior still depends on separate tests, not the full lab. |
| 7. No malformed-real-input corpus is generated. | The full lab emits clean `df`, `mount`, `fstab`, `iostat`, and `ps` files. | Real command outputs include locale differences, wrapped lines, headers, old sysstat fields, truncation, and partial captures. |
| 8. No root-only storage visibility case is generated. | Missing reason code: `ROOT_ONLY_STORAGE_VIEW`. | A common real assessment problem remains absent from the generated lab. |
| 9. No uncertain iostat mapping case is generated. | Missing reason code: `IOSTAT_DEVICE_MAPPING_UNCERTAIN`; all generated data maps cleanly. | Real LVM, multipath, encrypted, and device-mapper layouts often make attribution uncertain. |
| 10. LVM evidence is present but not behaviorally connected to mount sources. | Generated mounts use `/dev/sdb1`; generated `pvs/vgs/lvs` are simple supporting files. | It does not stress realistic `/dev/mapper/...`, `dm-*`, multipath, or layered mappings. |
| 11. Network filesystem variety is narrow. | Shared cases use NFS-style data; missing generated coverage for CIFS, SMB3, CephFS, GlusterFS, Lustre, GPFS, and SSHFS. | Different shared filesystems imply different operational and locking questions. |
| 12. Network mount options are simplistic. | Generated mount options are basic `rw,relatime`. | Real options such as hard/soft, locking, cache, version, credentials, and timeout settings may change risk. |
| 13. No non-data network filesystem ambiguity is generated. | Warning counts are empty. | The tool should be exercised against network mounts that are system, backup, home, or unknown context. |
| 14. Iostat samples are deterministic and smooth. | Each case has generated repeated values. | Real latency has spikes, warmup effects, idle intervals, and workload phase changes. |
| 15. No medium-latency cases are generated. | Missing reason code: `LATENCY_RISK_MEDIUM`. | Boundary behavior around medium risk is not covered by the full lab. |
| 16. No missing or unparseable iostat case is generated. | Missing reason codes: `IOSTAT_MISSING`, `IOSTAT_PARSE_FAILED`. | REVIEW behavior for absent or bad performance evidence is not represented in the full lab. |
| 17. Process evidence is too clean. | Each generated case has a small, clear process signal. | Real process lists are noisy, containerized, supervisor-heavy, and often include stale or unrelated services. |
| 18. No missing process-list case is generated. | Missing reason code: `PROCESS_LIST_MISSING`. | REVIEW behavior for missing process evidence is not represented in the full lab. |
| 19. No command-argument secret/redaction stress case is generated. | Generated process args are benign. | The redaction workflow needs adversarial coverage with tokens, URLs, DSNs, and credentials. |
| 20. No inactive-service or scheduled-job evidence is generated. | Process data is point-in-time only. | Backups, batch jobs, failover agents, and maintenance windows can dominate storage behavior. |
| 21. `du` evidence is perfectly aligned. | All generated `du-summary.txt` paths match candidate mounts. | Real `du` evidence can be scoped incorrectly, skipped, permission-limited, or collected on the wrong path. |
| 22. No inode-pressure case is generated. | Generated inode use is low and uniform. | Small-file-heavy workloads can fail or degrade even when byte capacity looks safe. |
| 23. File-size distribution and directory fanout are not measured. | The generator records owner-like metadata, not actual tree statistics. | Some storage choices depend on metadata density, not just GiB and await. |
| 24. Multi-VM topology is asserted, not observed. | Shared cases use generated owner-style fields and one bundle. | RWX requirements and active/active behavior need multi-host evidence to be defensible. |
| 25. Raw-device absence is not proved. | Raw block positive hints exist, but no negative-proof workflow exists. | The absence of raw hints in snapshots should not become a hard claim. |
| 26. No collection-window variability is generated. | Cases do not model peak, idle, backup, incident, or maintenance windows. | The same workload can produce different storage risk depending on timing. |
| 27. No growth-rate history is generated from observations. | Business fields are generated constants. | Capacity sizing still needs real growth, retention, purge, and churn data. |
| 28. No restore, backup, or failover evidence is observed. | Lifecycle fields are generated metadata. | Storage fit can depend on backup/restore and failover requirements. |
| 29. No proprietary-scan adversarial inputs are included. | Generated names are generic. | The scan mechanism is not stressed against realistic forbidden terms or customer/provider identifiers. |
| 30. No privacy-preserving owner mapping artifact is generated. | Redacted path meaning still depends on owner-held context. | Handoff usefulness requires a safe way to reconcile redacted paths with business meaning. |

### Output Decision Gaps

| Gap | Evidence From This Run | Why It Matters |
| --- | --- | --- |
| 31. No `FAIL` decisions are generated. | Fit distribution is `55 PASS`, `45 REVIEW`, `0 FAIL`. | A defensible core needs generated hard-failure scenarios, not only plausible-fit scenarios. |
| 32. No blockers are generated. | `blocker_counts` is empty. | Blocker handling and business escalation are not covered by the full lab. |
| 33. No no-match profile scenario is generated. | Missing reason code: `NO_STORAGE_CLASS_MATCH`; all cases have `STORAGE_CLASS_MATCH`. | The strongest business value often comes from finding capability gaps before pilots. |
| 34. No shared-filesystem-without-RWX failure is generated. | Missing reason code: `SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE`. | RWX absence is a major real platform blocker. |
| 35. No raw-block-required-without-profile failure is generated. | Missing reason code: `RAW_BLOCK_REQUIRED_NO_PROFILE`. | Raw block can be decisive and should be exercised as a hard incompatibility path. |
| 36. No capacity-exceeds-all-compatible-profile failure is generated. | Missing reason code: `CAPACITY_EXCEEDS_AVAILABLE_PROFILE`. | Oversized workloads are a common real storage blocker. |
| 37. No medium capacity risk is generated. | Missing reason code: `CAPACITY_RISK_MEDIUM`. | The decision boundary between PASS and REVIEW is not fully exercised. |
| 38. No medium latency risk is generated. | Missing reason code: `LATENCY_RISK_MEDIUM`. | The fast-tier recommendation boundary is not fully exercised. |
| 39. No low-latency tier recommendation is generated. | Missing reason code: `LOW_LATENCY_STORAGE_RECOMMENDED`. | If policy packs use low-latency tiers later, the generator does not cover that path. |
| 40. Raw-block cases stop at hint/review behavior. | `RAW_BLOCK_HINT` appears `5` times, but no raw-block blocker appears. | Hard raw-block requirement logic is not fully stress-tested. |
| 41. Warnings are absent. | `warning_counts` is empty. | Real reports often depend on warnings for human workflow; warning handling needs generated coverage. |
| 42. Missing-data output is absent. | All generated cases are complete. | Missing-data JSON and review behavior are not represented in generated full coverage. |
| 43. Rejected storage class diversity is limited by the complete profile. | Every case has at least one match. | The rejection matrix is less valuable without deliberate incompatible profile variants. |
| 44. Tie-breaking is not strongly stressed. | Generated classes have clear tier/kind distinctions. | Deterministic ranking needs cases with near-equivalent classes. |
| 45. Snapshot preference is not exercised. | Snapshot support varies, but no tie scenario forces snapshot-capable preference. | Secondary ranking logic can regress unnoticed. |
| 46. Expansion preference is not exercised at medium/high capacity. | Capacity high exists, but all matching paths remain structurally clean. | Expansion support should be tested where it changes recommendation order. |
| 47. Output realism is internally valid but not empirically validated. | All decisions validate, but trusted-label count is `0`. | Decision validation checks consistency, not correctness in the field. |
| 48. No false PASS or false REVIEW rate can be computed. | Corpus readiness is `RESEARCH_ONLY`. | Business defensibility needs measured error rates from trusted outcomes. |
| 49. No profile-drift decision set is generated. | Trend report uses two available decisions, not a deliberate profile-drift suite. | Storage-class changes over time are a real operating concern. |
| 50. No cross-version regression baseline is generated from this run. | This audit validates one current run. | A core technology needs repeatable comparison across engine versions and policy packs. |

### Business-Impact Gaps

| Gap | Evidence From This Run | Why It Matters |
| --- | --- | --- |
| 51. Business impact is simulated only. | Claim status is `SIMULATED_ONLY`. | Generated impact records cannot prove actual customer, partner, or platform value. |
| 52. Measured high-quality impact count is zero. | `measured_high_quality_impact_record_count` is `0`. | There is no empirical operational-impact claim yet. |
| 53. Trusted-label count is zero. | All `100` generated cases have `trusted_label: false`. | Generated reviews must not be counted as independent expert labels. |
| 54. Calibration-ready count is zero. | `calibration_ready_count` is `0`. | The generated lab cannot tune thresholds or claim model/rule accuracy. |
| 55. Follow-up work remains required for every generated case. | Follow-up SLA item count is `100`. | The workflow correctly demands real review/outcome/impact follow-up. |
| 56. No real assessment-time savings are measured. | Generated impact minutes are fixture values. | Operational-minute deltas need measured before/after assessment data. |
| 57. No real avoided failed pilot is recorded. | Avoided-pilot fields are generated. | This is a potentially high-value claim but needs accountable evidence. |
| 58. No real platform gap acceptance is recorded. | Platform-gap fields are generated. | Capability-gap decisions need owner/platform-team acceptance. |
| 59. No accountable real impact source exists. | Generated source is `generated-business-review`. | Business claims require named accountable source teams or owners. |
| 60. No baseline comparator was used in this run. | Business summary has generated impact records but no supplied baseline comparison artifact. | Time-savings claims need a baseline, otherwise they remain anecdotal. |
| 61. No monetization, revenue, conversion, or cost claims exist. | The repo intentionally avoids pricing. | Business impact must be framed operationally unless separate external financial data is supplied. |
| 62. No portfolio-level real decision value is shown. | This run validates generated individual cases. | Real business impact usually emerges from portfolio prioritization and avoided blocked pilots. |
| 63. No buyer/user workflow adoption data exists. | Artifacts show generated correctness, not usage. | Defensibility also depends on whether platform and application teams use the outputs. |
| 64. No cycle-time trend exists. | Trend report is structural, not an operational history. | Real impact needs repeated runs showing shorter assessment or fewer late blockers. |

### Corpus And Calibration Gaps

| Gap | Evidence From This Run | Why It Matters |
| --- | --- | --- |
| 65. Corpus readiness remains `RESEARCH_ONLY`. | Readiness blocker: `INSUFFICIENT_TRUSTED_LABEL_COVERAGE`. | The lab is not calibration-grade. |
| 66. Synthetic accuracy is not defensibility. | Generated decisions can match generated expectations by construction. | Field accuracy needs independent labels and outcomes. |
| 67. Negative controls are incomplete. | Generic stateful cases exist, but no no-data, wrong-profile, or no-match real controls exist. | PASS behavior needs controls that prove the tool does not over-escalate. |
| 68. Borderline thresholds are incomplete. | Medium capacity/latency reason codes are absent. | Threshold calibration needs cases near boundaries, not only low/high cases. |
| 69. Cross-reviewer disagreement is not generated at scale. | Generated reviews are consensus fixtures. | Adjudication workflow needs disagreement cases. |
| 70. Temporal repeats are not generated as a corpus family. | No same-workload repeated collection windows are present. | Repeatability and drift require repeated observations of the same workload. |
| 71. Profile drift is not generated as a corpus family. | No before/after profile constraints are generated. | Real platforms change classes, quotas, and capabilities. |
| 72. Policy-pack-specific readiness is not demonstrated. | Generated lab uses baseline policy only. | Domain policy packs need their own coverage and regression data. |
| 73. No real malformed-input cases are in the corpus. | Parser tests exist separately, but corpus does not include malformed real bundles. | Corpus evaluation should include degraded evidence, not only unit tests. |
| 74. No field-sourced workload-family distribution exists. | Family counts are chosen by the generator. | Business prioritization needs data from actual portfolios. |
| 75. No empirical reason-code distribution exists. | Reason-code counts are generated. | Rule priority and UI/report focus should be based on real frequency and impact. |

### Governance And Operational Gaps

| Gap | Evidence From This Run | Why It Matters |
| --- | --- | --- |
| 76. Handoff archive is checksum-based, not signed. | ZIP exists with manifest, but no signing key is used. | Regulated handoff may require signatures or external chain-of-custody controls. |
| 77. Attestation remains template-driven. | Owner/profile truth still requires external completion. | Templates are useful but do not enforce truth without process ownership. |
| 78. Quality gate can pass generated data for business-review mode. | Sample quality gate is `PASS` with warnings `CASE_HAS_NO_TRUSTED_LABEL` and `CORPUS_RESEARCH_ONLY`. | Gate mode selection must be governed; release/calibration gates should be used for stronger claims. |
| 79. Follow-up SLA is a static worklist, not an integrated workflow. | Follow-up items are generated JSON. | Real operations need assignment, reminders, escalation, and closure tracking outside or above the CLI. |
| 80. Proprietary scan depends on user-supplied terms. | No default banned-term list is bundled. | This is intentional, but organizations must supply their own scan policy. |
| 81. No external evidence repository integration exists. | All artifacts are local files. | Scaling field evidence requires durable storage, lineage, and access controls. |
| 82. No tamper-evident external timestamping exists. | Manifest is local SHA-256 only. | Strong defensibility may require external timestamping or signing. |
| 83. No automated threshold tuning exists. | Calibration actions remain recommendations. | Automatic tuning would require a trusted empirical corpus first. |
| 84. No release gate was run against production-ready evidence. | Corpus remains research-only. | A core technology needs a release gate backed by trusted cases. |
| 85. No human-review operating model is enforced by the repo. | The repo emits templates and worklists. | Business impact depends on clear ownership for review, outcome recording, and impact recording. |

## Assessment

The full-coverage generator is appropriate for software confidence: it creates complete, deterministic, realistic-enough evidence bundles and validates the end-to-end local workflow.

The remaining gaps are not mostly parser or report gaps. They are empirical evidence, adversarial coverage, negative-case generation, and operating-model gaps. The largest technical gaps are hard-failure generation, degraded-evidence generation, realistic device/topology complexity, and medium-risk boundary coverage. The largest business gaps are real trusted labels, real outcomes, measured operational impact, and governance around follow-up closure.

## Resolution Update

The 85 gaps above are now tracked to closure in `docs/LATEST_REALWORLD_GAP_CLOSURE_PROGRESS.md`.

The closure adds deterministic gap-closure cases for hard failures, degraded evidence, medium-risk boundaries, warnings, profile variants, and topology edge cases. It also adds governance controls for gaps that cannot be solved by generated data: real-world evidence contracts, attestation validation, operating model templates, chain-of-custody artifacts, and a stricter quality gate that blocks research-only generated corpora from business-review pass-through.
