# Gap Closure Status

This archived file tracked implementation progress against `docs/archive/core_technology_gap_register.md`.

Status meanings:

- `Closed`: implemented in code, documented, and covered by tests or objective repo evidence.
- `Partially covered`: the repo now has some capability, but the gap is not fully solved.
- `External evidence required`: the gap cannot be honestly closed without real field data, partner/user workflow evidence, operational metrics, or release activity outside this repository.
- `Open`: not implemented yet.

## Closed In This Pass

| Gap Area | Register Gap | Status | Closure Evidence |
| --- | --- | --- | --- |
| Real-world generator | Generator is only one hard-coded scenario mix. | Closed | `generate-real-world-data` now supports built-in estate profiles plus `--profile-config` for custom calibrated mixes. Each generated bundle writes `generator-profile.yml` and records profile metadata in `coverage.json`. Covered by `test_real_world_generator_supports_custom_calibration_profile`. |
| Real-world generator | No objective gate separates synthetic profiles from field-derived calibration profiles. | Closed | `validate-generator-profile --require-field-derived` fails synthetic profiles and accepts profiles declaring sanitized field-derived source metadata plus `calibration_evidence`. Covered by generator-profile validation tests. |
| Real-world generator | No repo workflow derives a field-calibrated profile from sanitized assessment evidence. | Closed | `derive-generator-profile` derives a strict-valid profile from a sanitized bundle assessment or assessment JSON and writes calibration evidence metadata. Covered by `test_derive_generator_profile_from_sanitized_bundle_assessment`. |
| Policy and scoring | Policy packs do not have expected-outcome regression assertions against a golden corpus. | Closed | `sanitize-corpus` now stores expected workload outcomes; `test-policy` re-evaluates policies and fails on outcome drift. Covered by `test_policy_corpus_command_fails_on_expected_outcome_regression`. |
| Policy and scoring | `test-policy` verifies loadability, not expected outcomes. | Closed | `test-policy` now reports `passed` or `failed`, counts failures, and exits non-zero on regression. |
| Corpus | No structural validation command for sanitized corpus cases. | Closed | `validate-corpus` validates required case files, redacted assessment loadability, fingerprints, and expected outcomes. Covered by passing and failing corpus validation tests. |
| Feedback | Feedback vocabulary lacks explicit accepted/rejected business outcome labels. | Closed | Feedback now supports `accepted`, `rejected`, `needs_more_data`, `duplicate`, and `wrong_motion` while retaining legacy labels. Covered by feedback summary tests. |
| Feedback | No false-positive measurement mechanism. | Closed | `feedback-summary` computes `false_positive_rate` from reviewed feedback labels. Covered by feedback metric tests. |
| Feedback | No false-negative measurement mechanism. | Closed | Feedback now supports `missed_opportunity` and `feedback-summary` reports `false_negative_count`. Covered by feedback metric tests. |
| Business impact | No manual-triage time benchmark mechanism. | Closed | Feedback files support manual/tool triage minutes and summaries compute saved minutes and percent. Covered by feedback metric tests. |
| Business impact | No conversion tracking mechanism. | Closed | Feedback items support `converted` and `next_step`; summaries compute conversion rate and next-step counts. Covered by feedback metric tests. |
| Repeated assessments | No repeated-run comparison mechanism. | Closed | `compare-assessments` reports workload, motion, confidence, and identity deltas. Covered by repeated-run comparison tests. |
| Business impact | No outcome ledger mechanism. | Closed | `outcome-ledger` aggregates feedback summaries across assessments. Covered by outcome ledger tests. |
| Generator calibration | No scenario frequency metadata. | Closed | Generator profile validation emits normalized scenario frequencies. Covered by generator-profile validation tests. |
| Generator calibration | No confidence intervals for scenario ratios. | Closed | Generator profile validation emits deterministic 95 percent Wilson intervals. Covered by generator-profile validation tests. |
| Generator calibration | No scenario correlation metadata. | Closed | Generator profile validation emits deterministic one-hot scenario correlations and documents the single-label limitation. Covered by generator-profile validation tests. |
| Generator coverage | No multi-source inventory generation. | Closed | `generate-real-world-data --multi-source` writes primary and secondary inventory files and manifest entries. Covered by multi-source bundle tests. |
| Generator coverage | No multi-source backup generation. | Closed | `generate-real-world-data --multi-source` writes primary and secondary backup files and manifest entries. Covered by multi-source bundle tests. |
| Generator coverage | No stale-export modeling. | Closed | Multi-source generation writes source-window metadata with an intentionally stale secondary inventory source, and bundle analysis flags it with `STALE_SOURCE_WINDOW`. |
| Generator coverage | No export-window skew modeling. | Closed | Multi-source generation writes different inventory, backup, and utilization source windows, and bundle analysis flags skew with `SOURCE_WINDOW_SKEW`. |
| Generator coverage | No partial-source coverage modeling. | Closed | Multi-source mode splits rows across files and bundle analysis verifies recovered total counts. Covered by multi-source bundle tests. |
| Generator coverage | No malformed CSV coverage. | Closed | `generate-real-world-data --edge-cases` writes malformed quoting, duplicate-header, embedded-newline, irregular-line-ending, extra-column, and missing-column fixtures. Adapter tests validate clear failure or structured readiness findings. |
| Generator coverage | No duplicate-header coverage. | Closed | CSV adapters emit `DUPLICATE_HEADER` findings and strict mode fails duplicate headers. Covered by edge-case validation tests. |
| Generator coverage | No embedded delimiter/newline coverage. | Closed | Edge-case fixtures include quoted commas and embedded newlines, and validation proves the adapter preserves one recognized record. |
| Generator coverage | No mixed-encoding coverage. | Closed | Edge-case fixtures include non-UTF-8 input and adapters fail with a clear UTF-8 error. |
| Generator coverage | No localization coverage. | Closed | Column aliases and fixtures now cover localized headers, dotted local dates, decimal-comma values, and localized power-state text. |
| Generator coverage | No unit variation coverage. | Closed | Parsers and edge fixtures cover MiB, GiB, TiB, thousands separators, decimal commas, and mixed units in one file. |
| Generator coverage | No contradictory record coverage. | Closed | Generator profiles now include `contradictory_records`, and adapters emit `IN_USE_EXCEEDS_PROVISIONED` plus `PERCENT_OUT_OF_RANGE` findings. Covered by validation and generator tests. |
| Generator coverage | No sparse estate coverage. | Closed | Generator profiles now include `sparse_minimal` rows with minimal identifiers and backup size only, exercising missing-evidence paths. |
| Generator coverage | No rich estate coverage. | Closed | Generator profiles now include `rich_context` rows with host, cluster, datacenter, policy, repository, and utilization context. |
| Generator coverage | No extreme outlier coverage. | Closed | Generator profiles now include `extreme_outlier` workloads with very high CPU, memory, backup footprint, restore points, and snapshot values. |
| Input readiness | No duplicate workload-row validation. | Closed | Identity resolution now emits severity-ranked `DUPLICATE_INVENTORY_UUID` and `DUPLICATE_INVENTORY_NAME` findings and marks affected workloads as duplicate candidates. |
| Input readiness | No duplicate backup-row severity ranking. | Closed | Top-level duplicate findings now distinguish inventory versus backup and treat duplicate UUIDs as error severity while names remain warning severity. |
| Input readiness | No suspicious range checks. | Closed | Adapters now flag negative values, percentages outside 0-100, and in-use storage greater than provisioned storage. |
| Input readiness | Validation does not produce a data-readiness grade. | Closed | `ValidationReport` now includes `readiness_score` and `readiness_grade`; CLI prints readiness. |
| Input readiness | Validation does not produce a structured remediation plan. | Closed | `ValidationReport` now includes `remediation_actions` with severity, field, action, and reason. |
| Input readiness | Missing-evidence requests are not aggregated into a data-request checklist. | Partially covered | Bundle summary now includes validation remediation actions. Workload-level missing evidence is not yet separately grouped by motion. |
| Input readiness | No matchability forecast before analysis. | Closed | `ValidationReport.matchability_forecast` reports UUID/name coverage, duplicate identifier counts, and high/medium/low matchability. Covered by validation tests. |
| Input readiness | No business severity classification for data problems. | Closed | Validation reports now include `business_severity_counts` derived from structured data-quality codes and fields. |
| Input readiness | No data-request checklist. | Closed | Validation reports and bundle readiness summaries now include prioritized `data_request_checklist` entries for missing recommended fields. |
| Input readiness | No field-level mapping confidence. | Closed | `field_profiles` now include per-field mapping confidence, blank rate, distinct count, samples, units, date formats, and warnings. |
| Input readiness | No sample parsed values for mapped columns. | Closed | `field_profiles.sample_values` exposes bounded samples for mapped fields and strict privacy redacts them in bundle validation output. |
| Input readiness | No mostly blank mapped-column detection. | Closed | Validation now emits `MAPPED_COLUMN_MOSTLY_BLANK` for mapped fields with at least 80 percent blanks. |
| Input readiness | No mixed unit or date-format detection. | Closed | Validation now emits `MIXED_UNITS` and `MIXED_DATE_FORMATS` from field profiles. |
| Input readiness | No cardinality-based mapping suspicion checks. | Closed | Validation now emits `LOW_CARDINALITY_IDENTIFIER` and `HIGH_CARDINALITY_CATEGORY` findings. |
| Input readiness | No stale input export detection. | Closed | Bundle analysis reads `source-metadata.yml` and emits `STALE_SOURCE_WINDOW` when one input is older than the newest source window. Covered by multi-source bundle tests. |
| Input readiness | No source-window alignment checks. | Closed | Bundle analysis emits `SOURCE_WINDOW_SKEW` when source windows span more than seven days. Covered by multi-source bundle tests. |
| Input readiness | No missing mapped-column detection. | Closed | Mapping files that reference absent columns fail validation with a clear error. Covered by mapping-reference tests. |
| Input readiness | No automatic mapping alternatives. | Closed | Validation reports now include `mapping_alternatives` for unmapped required/recommended fields based on conservative header similarity. Covered by mapping-alternative tests. |
| Input readiness | No mapping approval record. | Closed | Mapping specs now support `approved_by`, `approved_at_utc`, and `approval_notes`, and validation reports expose `mapping_approval`. Strict privacy redacts reviewer and notes. |
| Identity resolution | No identity override file. | Closed | `--identity-overrides` and bundle `identity_overrides` support reviewed inventory-to-backup mappings without editing raw CSVs. Covered by identity override tests. |
| Identity resolution | No historical-name support. | Partially covered | Identity overrides can map an inventory UUID/name to a backup historical name. Automated history discovery remains open. |
| Identity resolution | No workload alias support. | Partially covered | Identity overrides can express reviewed aliases. Alias graph management remains open. |
| Identity resolution | No controlled fuzzy matching. | Closed | Unique relaxed-name matching handles conservative punctuation/domain differences and emits `CONTROLLED_FUZZY_NAME_MATCH`. Covered by identity tests. |
| Identity resolution | No decomposed identity confidence. | Closed | Identity traces now include identifier, context, and conflict confidence factors. Covered by identity tests. |
| Identity resolution | No likely-cause classification for unmatched backup rows. | Closed | Identity resolution emits `UNMATCHED_BACKUP_LIKELY_DECOMMISSIONED` alongside unmatched backup rows. |
| Identity resolution | No field-friendly identity summaries. | Closed | Identity traces now include concise `field_summary` text. Covered by identity tests. |
| Identity resolution | No stable identity graph export. | Closed | Added `identity-graph` command with stable JSON nodes, edges, strategies, statuses, and confidence factors. Covered by identity graph tests. |
| Privacy | Validation JSON is not automatically redacted by privacy mode. | Closed | Bundle analysis now redacts validation report paths, warning text, finding messages, and finding source paths under strict privacy. Covered by bundle privacy test. |

## Partially Covered Before This Pass

| Gap Area | Current Coverage | Remaining Work |
| --- | --- | --- |
| Deterministic assessment kernel | Canonical evidence, provenance, identity states, feature traces, policy traces, ranking modes, redaction, fingerprints, and structured assessment JSON exist. | Needs schema artifacts, compatibility tests, release governance, and broader field corpus. |
| Real-world-like generated data | Deterministic generator covers all four business motions plus conflict, ambiguity, missing data, and unmatched scenarios. | Needs statistically calibrated distributions, malformed exports, localization, configurable estate profiles, repeated assessments, and feedback outcomes. |
| Identity resolution | UUID, normalized-name, conflict, duplicate-candidate, unmatched, and name-only paths exist. | Needs historical names, override files, context-aware matching, duplicate UUID handling, and remediation workflow. |
| Utilization-backed right-sizing | Optional utilization CSV supports p95 CPU and memory signals. | Needs time-windowed utilization, sustained-low-utilization tests, sparse sampling treatment, and utilization history. |
| Privacy | Assessment JSON and CSV can be redacted; strict mode redacts source paths in assessment evidence. | Needs custom privacy policies, output-wide privacy scanning, fingerprint privacy options, reversible local alias map, and threat model. |
| Feedback | Local feedback template and summary exist. | Needs accepted/rejected outcome analysis, policy effectiveness metrics, and conversion workflow. |
| Corpus | Sanitized corpus generation exists and now includes expected outcomes. | Needs a real sanitized field corpus and expected outcomes from reviewed assessments. |

## External Evidence Required

These cannot be marked closed by code alone:

1. A real sanitized field corpus.
2. Statistically grounded estate distributions. The repo now supports custom calibrated generator profiles, but actual statistical grounding requires sanitized field-derived profile files.
3. Field-labeled accepted, rejected, false-positive, and wrong-motion findings.
4. Proof that the tool creates more qualified assessment conversations than manual triage.
5. Proof that the tool saves time compared with spreadsheet assessment.
6. False-negative measurement, which requires reviewed opportunities the tool missed.
7. Assessment conversion tracking from input bundle to completed next step.
8. Partner enablement validation from real users.
9. Case-study-safe sanitized narratives based on real reviewed outcomes.
10. Commercial pricing and packaging evidence.

## Still Open By Area

### Real-World Data And Corpus

Open:

1. Sanitized field corpus from real assessments.
2. Distribution-driven generator.
3. Estate-size profiles.
4. Real field examples of multi-source inventory exports.
5. Real field examples of multi-source backup exports.
6. Automated severity scoring for partial-source coverage beyond current source-window checks.
7. Longitudinal corpus.
8. Feedback-labeled corpus.
9. Industry and organization-size stratification.
10. Non-comma delimiter coverage.
11. Real localization examples beyond the current synthetic edge fixtures.
12. Field-frequency weighting for unit variation cases.
13. Real field frequency for contradictory source records.
14. Real field sparse/rich estate examples beyond synthetic fixtures.
15. High-churn rename/clone/delete/restore cases.
16. Field-frequency weighting for extreme outlier cases.
17. Large-row-count benchmark corpus.

### Input Data Readiness

Closed:

1. Per-input readiness grade.
2. Per-input remediation actions.
3. Matchability forecast.
4. Business severity counts.
5. Data-request checklist.
6. Field-level mapping profiles and confidence.
7. Mostly blank mapped-column detection.
8. Mixed unit and mixed date-format detection.
9. Cardinality-based mapping suspicion checks.
10. Input export age detection through source-window metadata.
11. Source-window alignment checks.
12. Missing mapped-column detection.
13. Automatic mapping alternatives.
14. Mapping approval record.

Partially covered:

1. Workload-level missing evidence is not yet separately grouped by motion.

Open:

1. Full plausible range checks for every field not yet covered by current core numeric checks.
2. Duplicate workload-row remediation workflow.
3. Duplicate backup-row remediation workflow.
4. Kickoff-call intake scorecard.

### Identity Resolution

Closed:

1. Duplicate inventory UUIDs are now first-class error-severity findings.
2. Duplicate inventory names without UUIDs are now first-class warning-severity findings.
3. Affected duplicate inventory workloads are marked as `DUPLICATE_CANDIDATES`.
4. Reviewed identity overrides can resolve known source mismatches.
5. Identity override schema is exported through the CLI.
6. Controlled fuzzy matching handles unique relaxed-name cases.
7. Identity confidence is decomposed into identifier, context, and conflict factors.
8. Unmatched backup rows include a likely-cause classification.
9. Identity traces include field-friendly summaries.
10. Stable identity graph JSON export is available.

Open:

1. Full identity graph.
2. Automated historical-name discovery.
3. Context-aware identity matching.
4. Duplicate inventory row remediation workflow.
5. Duplicate UUID override workflow.
6. Clone/template relationships.
7. Alias graph management beyond reviewed point overrides.
8. Identity remediation workflow.
9. Incremental identity reconciliation across repeated runs.

### Feature Engineering

Closed:

1. Time-windowed utilization features include sample window days and sample quality.
2. Application context presence feature is available.
3. Protection-policy context presence feature is available.
4. Storage-efficiency features include provisioned-to-used and snapshot-to-used ratios.
5. Data-quality-derived features include finding count and risk level.
6. Feature confidence impact is summarized on each feature set.

Open:

1. Workload volatility features across repeated snapshots.
2. Full protection-policy fit logic against expected RPO/RTO classes.
3. Field-friendly feature summaries grouped for presentation.
4. Feature version migration.
5. Large-scale feature benchmarks.
6. Feature property tests.
7. Feature cache.
8. Plug-in feature API.
9. Feature-impact reports.

### Policy And Scoring

Closed:

1. Expected-outcome regression assertions for corpus cases.
2. Non-zero failure behavior for policy regressions.
3. Balanced ranking is the default and keeps top-N as a total row cap.
4. Policy packs support approval metadata.
5. Compatibility matrix is available through `schema --kind compatibility`.
6. Policy change-impact reporting is available through `policy-impact`.
7. Final confidence includes decomposed factors.
8. Missing-evidence requests include high/medium priority.
9. Blocking flags include severity and reason details.
10. Archive policy can use stale inventory last-seen evidence.
11. DR policy can flag long RPO values for review.
12. Right-sizing policy qualifies sparse utilization sample windows.

Open:

1. Field-calibrated scoring.
2. Cross-motion score comparability proof.
3. Policy pack library.
4. Field-tuned threshold guidance.
5. Full missing-evidence score penalties across every motion.
6. Full RTO policy-fit DR logic.
7. Dependency-complexity migration logic.
8. Formal explainability contract per motion.
9. Threshold sensitivity simulation.

### Output And Business Workflow

Closed:

1. Discovery-call plan is generated by `workflow-pack`.
2. Per-motion work queues are generated.
3. Work queues group by currently modeled context fields.
4. Executive summary Markdown is generated.
5. Strong-candidate, needs-more-data, and do-not-present classification is generated.
6. Evidence packets are generated.
7. Ranking-mode comparison is generated.
8. Task-system CSV export is generated.
9. Workflow state starts as `new` for queue items.
10. Workshop handoff pack artifacts are generated in one output directory.

Partially covered:

1. Remediation actions now appear in bundle summary.
2. Structured assessment JSON can support downstream workflow tools.

Open:

1. Grouping by application, owner, environment, or service beyond currently modeled context fields.
2. Related-finding clustering.
3. Outcome-quality summary.
4. Partner-specific templates.
5. Controlled natural-language report generation.
6. Batch comparison between assessments beyond pairwise comparison.

### Business Value And Commercial Defensibility

External evidence required:

1. Manual-triage comparison.
2. Field acceptance rate.
3. Time-saved baseline.
4. False-positive measurement.
5. False-negative measurement.
6. Conversion funnel.
7. Partner enablement proof.
8. Business-value taxonomy validation.
9. Rejection reason taxonomy validation.
10. Repeat-assessment improvement metrics.
11. Policy accuracy over time.
12. Sanitized case-study narratives.
13. Product analytics design validation.
14. Buyer/user split validation.
15. Packaging and pricing strategy.

### Privacy, Security, And Governance

Closed:

1. Strict privacy now applies to bundle validation JSON.
2. Output-wide privacy scan harness is available through `privacy-scan`.
3. Accidental secret-like pattern detection is included in `privacy-scan`.

Partially covered:

1. Assessment and CSV redaction.
2. Local fingerprints.
3. No external calls or credentials.

Open:

1. Custom field-level privacy policy.
2. Privacy review report.
3. Fingerprint privacy options.
4. Row-number and column-name suppression option.
5. Reversible local alias map.
6. Configurable salt policy.
7. Threat model.
8. Supply-chain hardening.
9. Signed releases.
10. Software bill of materials.
11. Privacy impact template.
12. Compliance mapping.

### Adapter And Integration

Open:

1. Robust arbitrary schema mapper.
2. XLSX input.
3. Multi-sheet workbook support.
4. Multiple inventory sources per bundle.
5. Multiple backup sources per bundle.
6. Mapping recommendations from approved mappings.
7. Messy export adapter tests.
8. Adapter compatibility suite.
9. Adapter metadata contract.
10. Schema drift detector.
11. Canonical input preview command.
12. Interactive mapping assistant.
13. Extension template.
14. Optional source-specific CSV mapper packages.
15. Offline database/snapshot imports.

### Engineering Quality And Release

Closed:

1. Local CI script is included.
2. Release process documentation is included.
3. Contribution guidelines are included.
4. Governance model is included.
5. Security reporting guidance is included.

Open:

1. Type checking.
2. Linting and formatting.
3. Performance benchmarks.
4. Property-based tests.
5. Property-based fuzz tests beyond the targeted malformed CSV regression cases.
6. Mutation tests.
7. JSON Schema release artifacts.
8. Contract compatibility tests.
9. CLI snapshot tests.
10. Clean install packaging test.
11. Dependency vulnerability scan.
12. Performance regression thresholds.
13. Large-file memory tests.
14. Golden-output checks for generated bundles.
15. Documentation build check.
16. Long-term support policy.

### Product Surface

Closed:

1. Guided end-to-end bundle workflow is available through `run-workflow`.
2. Highest-impact missing-evidence aggregation is available through `missing-evidence`.
3. Preview top findings is available through `preview-top-findings`.
4. Explain one workload is available through `explain-workload`.
5. Threshold descriptions are available through `describe-thresholds`.
6. Compact handoff ZIP export is available through `handoff-bundle`.
7. Assessment comparison command is available through `compare-assessments`.

Open:

1. Consistently actionable data-quality errors across every edge case.
2. Policy expected-outcome validation command is closed through `test-policy`; richer authoring workflow remains open.
3. Structured exit-code contract.
4. Shell-completion docs.
5. Full bundle lifecycle example.
6. Terminal mapping review interface.
7. Local desktop wrapper.
8. Web UI, intentionally not implemented.

### Documentation And Enablement

Open:

1. Real assessment engagement playbook.
2. Motion-specific field playbooks.
3. Confidence/blocking/missing-evidence interpretation guide.
4. Ranking strategy guide.
5. Mapper authoring guide.
6. Troubleshooting guide.
7. Data honesty FAQ.
8. Canonical field glossary.
9. Architecture decision records.
10. Generated schema docs.
11. Policy authoring guide.
12. Privacy guide.
13. Partner handoff guide.
14. Workshop training corpus.
15. Tutorial scripts.

## Current Position

The repo is stronger than a report generator: it now has a deterministic kernel, evidence traces, bundle workflow, redaction, generated data, readiness grading, and corpus-based policy regression enforcement.

It is not yet possible to honestly state that every gap is closed. The main unresolved blockers are real sanitized field data, outcome-labeled feedback, policy calibration, richer identity, field workflow artifacts, and engineering/release governance.
