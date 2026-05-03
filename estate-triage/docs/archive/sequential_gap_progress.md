# Sequential Gap Progress

This archived file tracked the strict gap-by-gap closure process requested after `docs/archive/real_world_generator_audit.md`.

Rule for this ledger: a gap is not marked done unless there is objective repo evidence. If a gap requires field evidence, the repo mechanism can be closed, but the field-evidence portion remains blocked until sanitized real data or operational results exist.

## Gap 1

Gap: The generator is synthetic-realistic, not statistically calibrated from real estates.

Closure criteria:

1. The generator must not be locked to a single hard-coded scenario distribution.
2. Built-in estate profiles must generate different deterministic estate mixes.
3. A custom profile file must allow field-derived scenario counts to drive generation.
4. Generated bundles must record which profile was used.
5. Tests must prove the custom calibration path controls row counts and profile metadata.
6. The documentation must state the remaining boundary: statistical truth requires sanitized field-derived profiles.

Implemented:

1. Added `EstateGeneratorProfile`.
2. Added built-in `coverage`, `smb`, `midmarket`, and `enterprise` profiles.
3. Added custom YAML profile support through `--profile-config`.
4. Added `generator-profile.yml` to generated bundles.
5. Added profile metadata to `coverage.json` and CLI JSON output.
6. Added regression coverage in `test_real_world_generator_supports_custom_calibration_profile`.
7. Added `estate-triage schema --kind generator-profile`.
8. Added `estate-triage validate-generator-profile --require-field-derived`.
9. Added regression coverage that fails synthetic profiles under field-derived enforcement.
10. Added regression coverage that accepts explicitly sanitized field-derived profiles.
11. Added required `calibration_evidence` metadata for strict field-derived profiles.
12. Added [generator_profile_calibration.md](generator_profile_calibration.md).
13. Updated README and closure ledger.

Status:

- Repo mechanism: closed.
- Real statistical calibration: external evidence required.

Reason the full gap cannot be honestly marked closed yet:

The repository can now validate and consume a sanitized field-derived calibration profile with calibration evidence metadata, and it can reject synthetic profiles when field-derived calibration is required. No actual sanitized field-derived profile has been supplied. Without that external evidence, the generator is configurable and calibration-ready, not field-calibrated.

Decision:

Repo-side closure is exhausted. The remaining requirement is external sanitized field-derived profile data. Per the updated user instruction, proceed to Gap 2 only because no further local implementation can create real field calibration evidence.

## Gap 2

Gap: No sanitized field-derived profile is included.

Closure criteria:

1. The repository must provide a way to derive a profile from sanitized assessment evidence.
2. The derived profile must include calibration evidence metadata.
3. The derived profile must pass strict field-derived validation.
4. Tests must prove the derivation path works.
5. The documentation must state that a real included profile still requires real reviewed assessments.

Implemented:

1. Added `derive_generator_profile_from_assessment`.
2. Added `estate-triage derive-generator-profile`.
3. The command can derive from a bundle's redacted assessment JSON or a direct assessment JSON path.
4. The derived profile includes `calibration_evidence`.
5. The command validates the derived profile with `--require-field-derived` by default.
6. Added regression coverage in `test_derive_generator_profile_from_sanitized_bundle_assessment`.
7. Updated [generator_profile_calibration.md](generator_profile_calibration.md) and README.

Status:

- Repo mechanism: closed.
- Included real field-derived profile: external evidence required.

Reason the full gap cannot be honestly marked closed yet:

The repository can derive and validate a field-derived profile from a sanitized assessment artifact, but no real sanitized assessment artifact has been supplied for inclusion. Creating one from synthetic examples would mislabel synthetic data as field-derived.

Repo-side closure is exhausted. The remaining requirement is external sanitized field-derived profile data. Proceed to Gap 3 because no further local implementation can include real data without fabricating it.

## Gap 3

Gap: No sanitized real assessment corpus.

Closure criteria:

1. The repository must support creating sanitized corpus cases.
2. Corpus cases must include redacted assessment artifacts.
3. Corpus cases must include input fingerprints.
4. Corpus cases must include expected outcomes.
5. The repository must provide a corpus validation command.
6. Tests must prove complete corpus cases pass and incomplete corpus cases fail.

Implemented:

1. `sanitize-corpus` already creates sanitized corpus cases from bundles.
2. Corpus cases include redacted `assessment.json`.
3. Corpus cases include `input-fingerprints.json`.
4. Corpus cases include `expected_outcomes`.
5. Added `estate-triage validate-corpus`.
6. Added regression coverage for passing and failing corpus validation.
7. Updated [real_world_data.md](real_world_data.md).

Status:

- Repo mechanism: closed.
- Real sanitized corpus content: external evidence required.

Reason the full gap cannot be honestly marked closed yet:

The repository can produce and validate sanitized corpus cases, but no real sanitized assessment corpus has been supplied for inclusion. Synthetic examples can test the mechanism, but they cannot substitute for real reviewed assessment shapes.

Repo-side closure is exhausted. The remaining requirement is real sanitized corpus content. Proceed to Gap 4 because no local implementation can fabricate real reviewed assessment shapes.

## Gap 4

Gap: No real accepted/rejected finding labels.

Closure criteria:

1. The repository must support accepted/rejected outcome labels.
2. The feedback vocabulary must support uncertainty and error classes.
3. Legacy feedback labels must remain readable.
4. Summary output must count the new labels.
5. Tests must prove the new labels are summarized.

Implemented:

1. Added `accepted`.
2. Added `rejected`.
3. Added `needs_more_data`.
4. Added `duplicate`.
5. Added `wrong_motion`.
6. Retained legacy `useful`, `not_useful`, `false_positive`, `wrong_match`, and `already_known`.
7. Updated the feedback template to use `accepted`.
8. Added regression coverage in `test_feedback_summary_supports_business_outcome_labels`.
9. Updated [real_world_data.md](real_world_data.md).

Status:

- Repo mechanism: closed.
- Real accepted/rejected field labels: external evidence required.

Reason the full gap cannot be honestly marked closed yet:

The repository can now record and summarize accepted/rejected field feedback, but no real reviewed feedback dataset has been supplied.

Repo-side closure is exhausted. The remaining requirement is a real reviewed feedback dataset. Proceed to Gap 5 because local implementation cannot invent reviewed labels.

## Gap 5

Gap: No false-positive measurement.

Closure criteria:

1. Feedback must have a `false_positive` outcome.
2. Feedback summary must compute a false-positive rate.
3. A CLI command must expose the metric.
4. Tests must verify the metric.

Implemented:

1. `false_positive` existed and is retained.
2. `wrong_match` is counted with false positives for quality-rate purposes.
3. `summarize_feedback` now emits `rates.false_positive_rate`.
4. Added `estate-triage feedback-summary`.
5. Added regression coverage in `test_feedback_summary_supports_business_outcome_labels` and `test_feedback_summary_cli_reports_business_metrics`.

Status:

- Repo mechanism: closed.
- Real false-positive measurement: external reviewed feedback required.

## Gap 6

Gap: No false-negative measurement.

Closure criteria:

1. Feedback must support a missed-opportunity label.
2. Feedback summary must count missed opportunities.
3. The CLI must expose the count.
4. Tests must verify the count.

Implemented:

1. Added `missed_opportunity`.
2. `summarize_feedback` now emits `rates.false_negative_count`.
3. `feedback-summary` exposes the count.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Real false-negative measurement: external reviewed missed-opportunity feedback required.

## Gap 7

Gap: No manual-triage time benchmark.

Closure criteria:

1. Feedback must record manual triage minutes.
2. Feedback must record tool triage minutes.
3. Summary must compute minutes and percent saved.
4. Tests must verify the benchmark.

Implemented:

1. Added `manual_triage_minutes`.
2. Added `tool_triage_minutes`.
3. `summarize_feedback` now emits `time_benchmark`.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Real time-saved proof: external measured workflow data required.

## Gap 8

Gap: No measured conversion from assessment to next-step work.

Closure criteria:

1. Feedback items must record conversion.
2. Feedback items must record next-step type.
3. Summary must compute conversion rate and next-step counts.
4. Tests must verify conversion metrics.

Implemented:

1. Added `converted`.
2. Added `next_step`.
3. `summarize_feedback` now emits `conversion`.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Real conversion proof: external reviewed workflow data required.

Repo-side closure is exhausted. The remaining requirement is real reviewed conversion data. Proceed to Gap 9 because local implementation cannot fabricate real conversion proof.

## Gap 9

Gap: No repeated real assessments over time.

Closure criteria:

1. The repository must compare two assessment outputs.
2. The comparison must show workload-count deltas.
3. The comparison must show motion, confidence, and identity-status deltas.
4. Tests must verify repeated-run comparison.

Implemented:

1. Added `estate_triage.compare`.
2. Added `estate-triage compare-assessments`.
3. Added repeated-run delta output.
4. Added regression coverage in `test_compare_assessments_reports_repeated_run_deltas`.

Status:

- Repo mechanism: closed.
- Real repeated assessment history: external evidence required.

## Gap 10

Gap: No real-world outcome ledger.

Closure criteria:

1. The repository must aggregate feedback across assessments.
2. The ledger must aggregate outcomes, rates, conversion, and time benchmark fields.
3. A CLI command must expose the ledger.
4. Tests must verify aggregation.

Implemented:

1. Added `summarize_feedback_ledger`.
2. Added `estate-triage outcome-ledger`.
3. Added aggregate outcome/rate/conversion/time metrics.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Real outcome ledger content: external reviewed feedback required.

## Gap 11

Gap: No field-derived scenario frequency metadata.

Closure criteria:

1. Generator profile validation must emit scenario frequencies.
2. Frequencies must be derived from profile counts.
3. Tests must verify frequency output.

Implemented:

1. `validate-generator-profile` now emits `scenario_frequencies`.
2. Frequencies are normalized from scenario counts.
3. Added regression coverage.

Status:

- Repo mechanism: closed.
- Real field-derived frequencies: external field-derived profile required.

## Gap 12

Gap: No confidence intervals for generator scenario ratios.

Closure criteria:

1. Generator profile validation must emit confidence intervals.
2. Intervals must be deterministic.
3. Tests must verify interval output.

Implemented:

1. Added 95 percent Wilson confidence intervals.
2. `validate-generator-profile` now emits `scenario_confidence_intervals_95`.
3. Added regression coverage.

Status:

- Repo mechanism: closed.
- Statistically meaningful intervals: external field-derived sample sizes required.

## Gap 13

Gap: No modeled correlation between scenario types.

Closure criteria:

1. Generator profile validation must emit scenario correlation metadata.
2. Correlations must be deterministic for the current single-label scenario model.
3. Documentation must explain the single-label limitation.
4. Tests must verify correlation output.

Implemented:

1. Added deterministic one-hot scenario correlation matrix.
2. `validate-generator-profile` now emits `scenario_correlations`.
3. Documented the single-label limitation.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Rich real-world multi-label correlation model: external field-derived multi-label evidence required.

Repo-side closure is exhausted. Proceed to Gap 14 because richer real-world correlation evidence requires external field data.

## Gap 14

Gap: No multi-source inventory input generation.

Closure criteria:

1. The generator must support more than one inventory file.
2. The generated manifest must include all inventory sources.
3. Bundle analysis must consume the split inventory sources.
4. Tests must verify total inventory row coverage.

Implemented:

1. Added `generate-real-world-data --multi-source`.
2. Multi-source generation writes `inputs/inventory.csv` and `inputs/inventory_secondary.csv`.
3. The manifest includes both inventory inputs.
4. Added regression coverage in `test_real_world_generator_supports_multi_source_bundle`.

Status:

- Repo mechanism: closed.
- Real multi-source field exports: external field data required.

## Gap 15

Gap: No multi-source backup input generation.

Closure criteria:

1. The generator must support more than one backup file.
2. The generated manifest must include all backup sources.
3. Bundle analysis must consume the split backup sources.
4. Tests must verify total backup row coverage.

Implemented:

1. `--multi-source` writes `inputs/backup_export.csv` and `inputs/backup_secondary.csv`.
2. The manifest includes both backup inputs.
3. Added regression coverage.

Status:

- Repo mechanism: closed.
- Real multi-source backup exports: external field data required.

## Gap 16

Gap: No stale-export modeling.

Closure criteria:

1. Generated data must include source-window metadata.
2. A generated source must intentionally model stale capture timing.
3. Tests must verify the metadata exists.

Implemented:

1. Multi-source generation writes `source-metadata.yml`.
2. `inputs/inventory_secondary.csv` is marked with an older source window.
3. Added regression coverage.

Status:

- Generator modeling mechanism: closed.
- Readiness scoring from source-window metadata: still open for later validation work.

## Gap 17

Gap: No export-window skew modeling.

Closure criteria:

1. Generated data must contain different capture windows for different source types.
2. Metadata must identify the skew.
3. Tests must verify the metadata exists.

Implemented:

1. `source-metadata.yml` records separate inventory, backup, and utilization windows.
2. Secondary backup intentionally uses a different capture window.
3. Added regression coverage.

Status:

- Generator modeling mechanism: closed.
- Automated source-window skew severity scoring: still open for validation work.

## Gap 18

Gap: No partial-source coverage modeling.

Closure criteria:

1. Generated rows must be split across sources rather than duplicated.
2. The manifest must retain all sources.
3. Bundle analysis must recover the full row count.
4. Tests must verify row totals.

Implemented:

1. Multi-source mode splits inventory and backup rows across primary and secondary files.
2. Bundle analysis recovers the expected total inventory and backup rows.
3. Added regression coverage.

Status:

- Repo mechanism: closed.
- Real partial-source field behavior: external field data required.

## Gap 19

Gap: No malformed CSV coverage.

Closure criteria:

1. Generated data must include malformed CSV structure.
2. The adapter must fail malformed quoting with a clear error.
3. Generated data must include irregular row shapes.
4. Validation must surface structured data-quality findings for recoverable row-shape problems.
5. Tests must verify both failure and recoverable-warning paths.

Implemented:

1. Added `generate-real-world-data --edge-cases`.
2. Edge-case generation writes `edge-cases/malformed_inventory.csv`.
3. CSV adapters now use strict CSV parsing and convert parser errors into `TriageError`.
4. Edge-case generation writes extra-column and missing-column fixtures.
5. CSV adapters now emit `EXTRA_CSV_COLUMNS` and `MISSING_CSV_COLUMNS`.
6. Added regression coverage in edge-case validation tests.

Status:

- Repo mechanism: closed.
- Real malformed export frequency: external field data required.

## Gap 20

Gap: No duplicate-header coverage.

Closure criteria:

1. Generated data must include duplicate headers.
2. Validation must report duplicate headers as structured data quality.
3. Strict mode must not silently continue on duplicate headers.
4. Tests must verify duplicate-header detection.

Implemented:

1. Edge-case generation writes `edge-cases/duplicate_headers_inventory.csv`.
2. CSV adapters now detect duplicate headers using normalized column keys.
3. Non-strict validation emits `DUPLICATE_HEADER`.
4. Strict mode raises a clear duplicate-header error.
5. Added regression coverage for the structured finding.

Status:

- Repo mechanism: closed.
- Real duplicate-header frequency: external field data required.

## Gap 21

Gap: No embedded delimiter or newline coverage.

Closure criteria:

1. Generated data must include quoted delimiters.
2. Generated data must include embedded newlines.
3. The adapter must read the fixture as one logical row.
4. Tests must verify validation succeeds.

Implemented:

1. Edge-case generation writes `edge-cases/embedded_delimiters_inventory.csv`.
2. The fixture contains a quoted comma and embedded newline inside the workload name.
3. Validation recognizes one inventory record from the file.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Real export frequency: external field data required.

## Gap 22

Gap: No mixed-encoding coverage.

Closure criteria:

1. Generated data must include a non-UTF-8 fixture.
2. The adapter must fail with a clear encoding error.
3. Tests must verify the error path.

Implemented:

1. Edge-case generation writes `edge-cases/non_utf8_inventory.csv`.
2. CSV adapters now catch `UnicodeDecodeError`.
3. Validation reports that the file is not valid UTF-8.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Encoding auto-detection and conversion workflow: intentionally not implemented in MVP.

## Gap 23

Gap: No localization coverage.

Closure criteria:

1. Generated data must include localized headers.
2. Generated data must include localized power-state values.
3. Generated data must include a localized date format that is unambiguous.
4. Generated data must include decimal-comma values.
5. Validation must accept these deterministic cases.
6. Tests must verify localized inventory and backup validation.

Implemented:

1. Added localized aliases for inventory, backup, and utilization identity fields.
2. Added localized aliases for inventory power, CPU, memory, used storage, and OS fields.
3. Added localized backup total alias.
4. Added localized power-state token support for deterministic on/off flags.
5. Added unambiguous dotted date parsing.
6. Added decimal-comma numeric parsing when the separator is unambiguous.
7. Edge-case generation writes localized inventory and backup fixtures.
8. Added regression coverage for localized validation.

Status:

- Repo mechanism: closed for deterministic synthetic coverage.
- Broad real localization corpus: external field data required.

## Gap 24

Gap: No mixed-unit coverage.

Closure criteria:

1. Generated data must include mixed MiB/GiB/TiB values in one input class.
2. Parsers must normalize mixed units to MiB.
3. Parsers must preserve existing thousands-separator behavior.
4. Tests must verify mixed units and decimal-comma values.

Implemented:

1. Edge-case generation writes `edge-cases/mixed_units_inventory.csv`.
2. Storage parsing now handles mixed units plus deterministic decimal-comma values.
3. Numeric parsing now handles deterministic decimal-comma percentages.
4. Existing thousands-separator behavior remains covered.
5. Added parser and generated-fixture regression coverage.

Status:

- Repo mechanism: closed.
- Field-frequency weighting for mixed units: external field data required.

## Gap 25

Gap: No contradictory record coverage.

Closure criteria:

1. Generated data must include contradictory numeric source records.
2. Validation must flag in-use storage greater than provisioned storage.
3. Validation must flag percentages outside 0-100.
4. Tests must verify the structured findings.

Implemented:

1. Added `contradictory_records` to generator profiles.
2. Added adapter range checks for `IN_USE_EXCEEDS_PROVISIONED`.
3. Added adapter range checks for `PERCENT_OUT_OF_RANGE`.
4. Added broader negative-value checks for numeric fields.
5. Added regression coverage for validation output and generator coverage.

Status:

- Repo mechanism: closed.
- Real contradictory-record frequency: external field data required.

## Gap 26

Gap: No sparse-estate coverage.

Closure criteria:

1. Generated data must include rows with only minimal identity and backup size.
2. The rows must exercise missing-evidence paths without crashing.
3. The generated coverage summary must expose the scenario count.

Implemented:

1. Added `sparse_minimal` to generator profiles.
2. Sparse rows intentionally omit power, CPU, memory, storage-used, OS, restore point, restore count, and change-rate evidence.
3. Generator coverage tests verify the scenario is present.

Status:

- Repo mechanism: closed.
- Real sparse-estate field examples: external field data required.

## Gap 27

Gap: No rich-estate coverage.

Closure criteria:

1. Generated data must include rows with richer infrastructure and backup context.
2. The rows must include utilization context.
3. The generated coverage summary must expose the scenario count.

Implemented:

1. Added `rich_context` to generator profiles.
2. Rich rows include datacenter, cluster, host, backup policy, repository, and utilization.
3. Generator coverage tests verify the scenario is present.

Status:

- Repo mechanism: closed for currently modeled context fields.
- Ownership, application, service, and dependency fields remain future feature work.

## Gap 28

Gap: No backup-only records caused by decommissioned workloads.

Closure criteria:

1. Generated data must include backup rows with no inventory match.
2. Analysis must not crash.
3. Data quality must include unmatched backup rows.

Implemented:

1. Existing generator profiles include `backup_only_unmatched_rows`.
2. Identity resolution emits `UNMATCHED_BACKUP_ROWS`.
3. Generator coverage tests verify unmatched backup behavior through assessment data quality.

Status:

- Repo mechanism: closed.
- Real decommissioned-workload evidence: external field data required.

## Gap 29

Gap: No inventory-only records caused by new workloads not yet in backup policy.

Closure criteria:

1. Generated data must include inventory rows without backup matches.
2. Analysis must not crash.
3. Findings must include no-backup-match signals.

Implemented:

1. Existing generator profiles include `no_backup_match`.
2. Identity resolution emits `UNMATCHED_INVENTORY`.
3. Policy output includes no-backup-match blocking flags and reason codes where applicable.
4. Generator coverage tests verify unmatched inventory behavior.

Status:

- Repo mechanism: closed.
- Real new-workload backup onboarding evidence: external field data required.

## Gap 30

Gap: No extreme outlier cases.

Closure criteria:

1. Generated data must include extreme CPU, memory, snapshot, backup footprint, and restore-point values.
2. Analysis must remain deterministic.
3. The generated coverage summary must expose the scenario count.

Implemented:

1. Added `extreme_outlier` to generator profiles.
2. Outlier rows include very high allocated CPU, memory, backup size, restore-point count, and snapshot footprint.
3. Generator coverage tests verify the scenario is present.

Status:

- Repo mechanism: closed.
- Field-frequency weighting for outliers: external field data required.

## Gap 31

Gap: Duplicate inventory rows and duplicate UUIDs are not first-class identity conditions.

Closure criteria:

1. Duplicate inventory UUIDs must produce explicit data-quality findings.
2. Duplicate inventory names without UUIDs must produce explicit data-quality findings.
3. Duplicate UUIDs must be severity-ranked higher than duplicate names.
4. Affected workloads must not look fully resolved.
5. Tests must verify duplicate inventory UUID behavior.

Implemented:

1. Identity resolution now indexes inventory records by UUID and normalized name.
2. It emits `DUPLICATE_INVENTORY_UUID` with error severity.
3. It emits `DUPLICATE_INVENTORY_NAME` with warning severity.
4. Affected workloads are marked `DUPLICATE_CANDIDATES` with low confidence.
5. Duplicate backup findings now distinguish backup UUID and backup name duplicates with severity ranking.
6. Added regression coverage.

Status:

- Repo mechanism: closed.
- Identity override and remediation workflow: still open.

## Gap 32

Gap: Validation does not estimate matchability before analysis.

Closure criteria:

1. Validation must report UUID coverage.
2. Validation must report name coverage.
3. Validation must report duplicate UUID and duplicate name counts.
4. Validation must emit an overall matchability forecast.
5. Tests must verify the field exists.

Implemented:

1. Added `MatchabilityForecast`.
2. Validation reports now include `matchability_forecast`.
3. The forecast is high, medium, or low based on identifier coverage and duplicates.
4. Added regression coverage through validation JSON tests.

Status:

- Repo mechanism: closed.
- Cross-input matchability before bundle analysis can be deepened with source-window context later.

## Gap 33

Gap: Validation does not assign business severity to data problems.

Closure criteria:

1. Validation must classify data-quality problems by business severity.
2. The classification must be structured JSON.
3. Tests must verify severity output is present.

Implemented:

1. Added data-quality-to-business-severity classification.
2. Validation reports now include `business_severity_counts`.
3. High-impact identity and backup/storage fields are ranked above low-impact optional fields.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Field-tuned severity weights require reviewed field outcomes.

## Gap 34

Gap: Validation does not produce a data-request checklist.

Closure criteria:

1. Validation must emit explicit request items.
2. Request items must include priority, field, request text, and reason.
3. Bundle readiness summaries must aggregate the checklist.
4. Tests must verify the checklist exists.

Implemented:

1. Added `DataRequestItem`.
2. Validation reports now include `data_request_checklist`.
3. Bundle readiness summaries now aggregate checklist items across inputs.
4. Added regression coverage for empty checklist behavior on complete utilization input.

Status:

- Repo mechanism: closed.
- Motion-specific missing-evidence grouping remains future workflow work.

## Gap 35

Gap: Validation does not provide field-level confidence scores for mapped columns.

Closure criteria:

1. Validation must profile mapped fields.
2. Each profile must include a confidence value.
3. Confidence must drop for suspicious mapped columns.
4. Tests must verify low-confidence mapping suspicion.

Implemented:

1. Added `FieldProfile`.
2. Field profiles include `mapping_confidence`.
3. Mapping confidence falls to medium or low when blankness, mixed formats, or cardinality warnings appear.
4. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 36

Gap: Validation does not show sample parsed values for mapped columns.

Closure criteria:

1. Field profiles must include bounded sample values.
2. Strict privacy must redact samples in bundle validation output.
3. Tests must verify field profiles exist.

Implemented:

1. Field profiles now include up to three distinct sample values.
2. Strict bundle privacy redacts `sample_values`.
3. Added regression coverage that field profiles are emitted.

Status:

- Repo mechanism: closed.

## Gap 37

Gap: Validation does not detect mapped columns that are mostly blank.

Closure criteria:

1. Field profiles must compute blank percentage.
2. Mostly blank mapped fields must create a data-quality finding.
3. Readiness scoring must account for the finding.

Implemented:

1. Field profiles now include `blank_pct`.
2. Validation emits `MAPPED_COLUMN_MOSTLY_BLANK` at 80 percent blankness or higher.
3. Profile-derived findings feed the existing readiness score.

Status:

- Repo mechanism: closed.

## Gap 38

Gap: Validation does not detect mixed units or mixed date formats.

Closure criteria:

1. Field profiles must detect storage units.
2. Field profiles must detect date format families.
3. Mixed units and mixed date formats must create data-quality findings.
4. Tests must verify both findings.

Implemented:

1. Added unit detection to field profiles.
2. Added date-format family detection to field profiles.
3. Validation emits `MIXED_UNITS` and `MIXED_DATE_FORMATS`.
4. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 39

Gap: Validation does not detect low-cardinality fields that are probably incorrectly mapped.

Closure criteria:

1. Identifier fields must be checked for suspiciously low cardinality.
2. A structured finding must be emitted.
3. Tests must verify the finding.

Implemented:

1. Field profiles check `uuid` and `name` cardinality.
2. Validation emits `LOW_CARDINALITY_IDENTIFIER`.
3. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 40

Gap: Validation does not detect high-cardinality fields that are probably identifiers rather than categories.

Closure criteria:

1. Category-like fields must be checked for suspiciously high cardinality.
2. A structured finding must be emitted.
3. Tests must verify the finding.

Implemented:

1. Field profiles check category-like fields such as power state, OS, policy, and repository.
2. Validation emits `HIGH_CARDINALITY_CATEGORY`.
3. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 41

Gap: Validation does not identify stale input files from manifest timestamps or embedded export timestamps.

Closure criteria:

1. Bundle analysis must read source-window metadata when present.
2. Inputs older than the newest bundle source window must be flagged.
3. The finding must appear in readiness summary output.
4. Tests must verify stale-source detection.

Implemented:

1. Bundle analysis now reads `source-metadata.yml`.
2. It parses single timestamps and timestamp ranges.
3. It emits `STALE_SOURCE_WINDOW` when an input is more than 30 days older than the newest source.
4. The finding is added to validation readiness output and summary readiness output.
5. Added regression coverage through the generated multi-source bundle.

Status:

- Repo mechanism: closed.
- Embedded export timestamp extraction from arbitrary CSV columns remains future adapter work.

## Gap 42

Gap: Validation does not detect whether inventory, backup, and utilization windows are aligned.

Closure criteria:

1. Bundle analysis must compare all source windows when metadata exists.
2. Excessive skew must produce a structured finding.
3. Readiness output must expose the finding.
4. Tests must verify skew detection.

Implemented:

1. Bundle analysis now computes source-window spread.
2. It emits `SOURCE_WINDOW_SKEW` when windows span more than seven days.
3. Readiness summary includes `source_window_findings`.
4. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 43

Gap: Validation does not detect if a mapping file references columns absent from the input.

Closure criteria:

1. Validation must fail when a mapping references a missing source column.
2. The error must be clear.
3. Tests must verify the failure path.

Implemented:

1. Existing effective mapping validation fails absent mapped columns.
2. Added regression coverage for the CLI validation path.

Status:

- Repo mechanism: closed.

## Gap 44

Gap: Validation does not generate automatic mapping alternatives with confidence.

Closure criteria:

1. Validation reports must include suggested mappings for unmapped required or recommended fields.
2. Suggestions must include confidence and reason.
3. Suggestions must be conservative enough to require human review rather than silently mapping.
4. Tests must verify suggestions.

Implemented:

1. Added `MappingAlternative`.
2. Validation reports now include `mapping_alternatives`.
3. Alternatives are generated from conservative header-label similarity and include confidence scores.
4. Added regression coverage.

Status:

- Repo mechanism: closed.
- Human approval is still required before using a suggested mapping.

## Gap 45

Gap: Validation does not preserve a human approval record for mapping decisions.

Closure criteria:

1. Mapping specs must support approval metadata.
2. Validation reports must expose approval metadata.
3. Strict privacy must redact human-identifying approval fields.
4. Tests must verify approval output.

Implemented:

1. Added `approved_by`, `approved_at_utc`, and `approval_notes` to `ColumnMapping`.
2. Added `MappingApproval` to validation reports.
3. Strict bundle validation redaction redacts reviewer and approval notes.
4. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 46

Gap: There is no user-supplied identity override file to resolve known conflicts without editing source CSVs.

Closure criteria:

1. The repository must define an override schema.
2. CLI analysis must accept an override file.
3. Bundle analysis must accept an override file.
4. Overrides must leave an audit finding.
5. Tests must verify override behavior.

Implemented:

1. Added `IdentityOverride` and `IdentityOverrideSet`.
2. Added `--identity-overrides` to `analyze`.
3. Added `identity_overrides` to bundle manifests.
4. Added `IDENTITY_OVERRIDE_APPLIED` and `IDENTITY_OVERRIDE_UNRESOLVED`.
5. Added `schema --kind identity-overrides`.
6. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 47

Gap: Historical names are not supported.

Closure criteria:

1. A reviewed mapping must be able to connect a current inventory row to a historical backup name.
2. The match must be auditable.
3. Tests must verify the path.

Implemented:

1. Identity overrides can map `inventory_uuid` or `inventory_name` to `backup_name`.
2. The resulting match uses `identity_override` strategy and records an audit finding.
3. Added regression coverage for a known rename.

Status:

- Reviewed override mechanism: closed.
- Automated historical-name discovery: still open.

## Gap 48

Gap: Workload aliases are not supported.

Closure criteria:

1. A reviewed alias must be expressible without editing raw CSVs.
2. The alias match must be explicit in identity traces.

Implemented:

1. Identity overrides can express reviewed aliases through inventory and backup name fields.
2. Identity traces expose the `identity_override` strategy.

Status:

- Reviewed point alias mechanism: closed.
- Full alias graph management: still open.

## Gap 49

Gap: Controlled fuzzy matching is not supported.

Closure criteria:

1. Fuzzy matching must be conservative and deterministic.
2. It must only apply after UUID and exact normalized-name matching fail.
3. It must only match unique relaxed-name candidates.
4. It must emit an explicit data-quality finding.
5. Tests must verify the path.

Implemented:

1. Added relaxed-name matching for punctuation/domain differences.
2. The strategy is `controlled_relaxed_name`.
3. It emits `CONTROLLED_FUZZY_NAME_MATCH`.
4. Confidence remains low and field summary tells the user to review the match.
5. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 50

Gap: Identity confidence is not decomposed.

Closure criteria:

1. Identity traces must separate identifier strength, context strength, and conflict state.
2. Tests must verify the factors.

Implemented:

1. Added `confidence_factors` to `IdentityTrace`.
2. Factors include `identifier`, `context`, and `conflict`.
3. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 51

Gap: Unmatched backup rows are not categorized by likely cause.

Closure criteria:

1. Unmatched backup rows must receive a structured likely-cause code.
2. The code must avoid claiming certainty.

Implemented:

1. Identity resolution now emits `UNMATCHED_BACKUP_LIKELY_DECOMMISSIONED`.
2. The message states that rows may represent decommissioned, renamed, or otherwise missing inventory workloads.

Status:

- Repo mechanism: closed.
- More precise cause classification will require field feedback and source context.

## Gap 52

Gap: Identity traces are useful for engineers but not summarized for field review.

Closure criteria:

1. Identity traces must include a concise field-friendly summary.
2. Tests must verify summary presence.

Implemented:

1. Added `field_summary` to `IdentityTrace`.
2. Summaries cover UUID match, name match, reviewed override, fuzzy match, conflicts, duplicates, and unmatched rows.
3. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 53

Gap: There is no stable identity graph export for downstream tools.

Closure criteria:

1. CLI must export identity graph JSON.
2. Export must include nodes, edges, strategy, status, matched-by, confidence, and confidence factors.
3. Tests must verify output.

Implemented:

1. Added `identity_graph_payload`.
2. Added `estate-triage identity-graph`.
3. Added regression coverage.

Status:

- Repo mechanism: closed.
- Richer cross-run graph reconciliation remains future work.

## Gap 54

Gap: Feature engineering lacks application-context features.

Closure criteria:

1. Feature output must indicate whether contextual inventory fields exist.
2. Tests must verify the feature.

Implemented:

1. Added `application_context_present`.
2. The feature checks datacenter, cluster, host, tags, and notes.
3. Added regression coverage.

Status:

- Repo mechanism: closed for currently modeled context fields.

## Gap 55

Gap: Feature engineering lacks protection-policy context features.

Closure criteria:

1. Feature output must indicate whether backup policy context exists.
2. Tests must verify the feature.

Implemented:

1. Added `protection_policy_context_present`.
2. The feature checks backup policy, retention days, RPO hours, and RTO tier.
3. Added regression coverage.

Status:

- Repo mechanism: closed for context presence.
- Full policy-fit evaluation remains future scoring work.

## Gap 56

Gap: Feature engineering lacks storage-efficiency features.

Closure criteria:

1. Feature output must include provisioned-to-used ratio.
2. Feature output must include snapshot-to-used ratio.
3. Tests must verify the features.

Implemented:

1. Added `provisioned_to_used_ratio`.
2. Added `snapshot_to_used_ratio`.
3. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 57

Gap: Feature engineering lacks data-quality-derived features.

Closure criteria:

1. Feature output must include data-quality finding count.
2. Feature output must include data-quality risk.
3. Tests must verify both.

Implemented:

1. Added `data_quality_finding_count`.
2. Added `data_quality_risk`.
3. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 58

Gap: Feature confidence is not separated from final recommendation confidence.

Closure criteria:

1. Feature sets must summarize feature-level confidence impacts.
2. Tests must verify the summary.

Implemented:

1. Added `confidence_summary` to `FeatureSet`.
2. The summary counts feature confidence-impact classes.
3. Added regression coverage.

Status:

- Repo mechanism: closed.
- More detailed calibrated confidence scoring remains future work.

## Gap 59

Gap: The default ranking strategy can bury commercially important motions.

Closure criteria:

1. Default ranking must keep `top_n` as a total row cap.
2. Default ranking must spread rows across motions when multiple motions have candidates.
3. Global ranking must remain available.
4. Tests must verify balanced behavior.

Implemented:

1. Added `balanced` ranking mode.
2. Made `balanced` the default for direct analysis, bundle analysis, and rank helper calls.
3. Kept `global` and `per_motion` available.
4. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 60

Gap: Policy approval workflow is absent.

Closure criteria:

1. Policy packs must carry approval metadata.
2. The default policy must include approval metadata.
3. Tests must verify metadata.

Implemented:

1. Added `approved_by`, `approved_at_utc`, and `approval_notes` to `PolicyPack`.
2. Added approval metadata to the default policy pack.
3. Added regression coverage.

Status:

- Repo mechanism: closed for metadata.
- External governance process remains organizational work.

## Gap 61

Gap: There is no policy compatibility matrix for schema versions, feature versions, and assessment versions.

Closure criteria:

1. Policy packs must declare compatible schema versions.
2. CLI must expose a compatibility matrix.
3. Tests must verify output.

Implemented:

1. Added `compatible_schema_versions` to `PolicyPack`.
2. Added default policy compatibility metadata.
3. Added `schema --kind compatibility`.
4. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 62

Gap: Policy change-impact reporting is not implemented.

Closure criteria:

1. CLI must compare a candidate policy against a baseline policy on an existing assessment artifact.
2. Output must count motion changes and score changes.
3. Tests must verify the command.

Implemented:

1. Added `policy_change_impact`.
2. Added `estate-triage policy-impact`.
3. The report includes workload count, changed primary motions, score changes, average score delta, and per-workload deltas.
4. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 63

Gap: Final confidence is not decomposed.

Closure criteria:

1. Workload assessments must expose confidence factors.
2. Tests must verify factors exist.

Implemented:

1. Added `confidence_factors` to `WorkloadAssessment`.
2. Factors include identity, metrics, right-sizing basis, and data-quality risk.
3. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 64

Gap: Missing evidence is not impact-ranked.

Closure criteria:

1. Missing-evidence requests must include priority.
2. High-impact fields must be marked high.
3. Tests must verify priority.

Implemented:

1. Added `priority` to `MissingEvidenceRequest`.
2. Identity, backup size, storage used, change rate, restore point, and utilization fields are high priority.
3. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 65

Gap: Blocking flag severities are absent.

Closure criteria:

1. Blocking flags must include structured severity and reason details.
2. Tests must verify blocking flag behavior.

Implemented:

1. Added `BlockingFlagDetail`.
2. Workload assessments now include `blocking_flag_details`.
3. Added severity mapping for existing blocking flags and sparse utilization windows.

Status:

- Repo mechanism: closed.

## Gap 66

Gap: Archive logic does not use last-powered-on or last-seen evidence.

Closure criteria:

1. Feature engine must compute inventory recency.
2. Archive policy must use stale last-seen evidence.
3. Tests must verify reason code.

Implemented:

1. Added `last_seen_age_days`, `last_powered_on_age_days`, and `stale_inventory_seen`.
2. Added `archive.stale_inventory_seen`.
3. Added regression coverage.

Status:

- Repo mechanism: closed for last-seen evidence.
- More nuanced last-powered-on policy remains future tuning.

## Gap 67

Gap: DR policy does not use RPO/RTO fit signals.

Closure criteria:

1. Feature engine must expose RPO.
2. DR policy must flag RPO review candidates.
3. Tests must verify reason code.

Implemented:

1. Added `rpo_hours`.
2. Added `long_rpo_review`.
3. Added `dr.long_rpo_review` reason code `RPO_REVIEW`.
4. Added regression coverage.

Status:

- RPO review mechanism: closed.
- Full RTO fit scoring remains future work.

## Gap 68

Gap: Right-sizing policy is not observation-window aware.

Closure criteria:

1. Policy must distinguish qualified and sparse utilization windows.
2. Sparse windows must be visible in policy output.
3. Tests must verify the behavior.

Implemented:

1. Existing utilization sample-quality feature is now used by policy.
2. Added `UTILIZATION_WINDOW_QUALIFIED`.
3. Added `SPARSE_UTILIZATION_WINDOW`.
4. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 69

Gap: Output lacks a discovery-call plan.

Implemented:

1. Added `workflow-pack`.
2. It writes `discovery-plan.md` grouped by motion.

Status:

- Repo mechanism: closed.

## Gap 70

Gap: Output lacks per-motion work queues.

Implemented:

1. Added `work-queues.json`.
2. Queues are grouped by primary motion and sorted by score.

Status:

- Repo mechanism: closed.

## Gap 71

Gap: Output lacks strong-candidate versus needs-more-data separation.

Implemented:

1. Queue items now include `presentation_class`.
2. Classes include `strong_candidate`, `needs_more_data`, `review_candidate`, and `do_not_present`.

Status:

- Repo mechanism: closed.

## Gap 72

Gap: Output lacks a do-not-present filter.

Implemented:

1. Queue classification marks conflicted, duplicate, and no-backup-match items as `do_not_present`.

Status:

- Repo mechanism: closed.

## Gap 73

Gap: Output lacks workload evidence packets.

Implemented:

1. Added `evidence-packets.json`.
2. Packets include confidence factors, identity summaries, key features, reason codes, blocking flag details, and missing evidence.

Status:

- Repo mechanism: closed.

## Gap 74

Gap: Output lacks ranking-mode comparison.

Implemented:

1. Added `ranking-mode-comparison.json`.
2. It compares all ranking modes for the same assessment and top-N.

Status:

- Repo mechanism: closed.

## Gap 75

Gap: Output lacks task-system export.

Implemented:

1. Added `tasks.csv`.
2. Rows include workflow state, motion, workload key, presentation class, score, and confidence.

Status:

- Repo mechanism: closed.

## Gap 76

Gap: Output lacks workflow state model.

Implemented:

1. Queue items and task rows include initial state `new`.

Status:

- Repo mechanism: closed for initial local state.

## Gap 77

Gap: Output lacks executive summary or Markdown renderer.

Implemented:

1. Added `executive-summary.md`.
2. Added `discovery-plan.md`.

Status:

- Repo mechanism: closed.

## Gap 78

Gap: Output lacks a workshop handoff pack.

Implemented:

1. `workflow-pack` writes all workflow artifacts into a single output directory.
2. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 79

Gap: Product surface lacks guided end-to-end workflow command.

Implemented:

1. Added `run-workflow`.
2. It analyzes a bundle and writes workflow artifacts.

Status:

- Repo mechanism: closed.

## Gap 80

Gap: Product surface lacks highest-impact missing-evidence command.

Implemented:

1. Added `missing-evidence`.
2. It aggregates missing fields by priority from assessment JSON.

Status:

- Repo mechanism: closed.

## Gap 81

Gap: Product surface lacks preview-top-findings command.

Implemented:

1. Added `preview-top-findings`.
2. It ranks assessment JSON without rewriting CSV outputs.

Status:

- Repo mechanism: closed.

## Gap 82

Gap: Product surface lacks explain-one-workload command.

Implemented:

1. Added `explain-workload`.
2. It returns identity trace, confidence factors, winning motion, blocking flags, missing evidence, and features.

Status:

- Repo mechanism: closed.

## Gap 83

Gap: Product surface lacks threshold description command.

Implemented:

1. Added `describe-thresholds`.
2. It emits threshold values and descriptions.

Status:

- Repo mechanism: closed.

## Gap 84

Gap: Product surface lacks compact handoff bundle export.

Implemented:

1. Added `handoff-bundle`.
2. It zips a local workflow or output directory without external calls.

Status:

- Repo mechanism: closed.

## Gap 85

Gap: Privacy controls lack an output-wide redaction scan harness and accidental secret detection.

Implemented:

1. Added `privacy-scan`.
2. The command scans files or directories locally.
3. It supports user-supplied forbidden literals through `--needle`.
4. It detects simple secret-like assignments and private-key headers.
5. It exits non-zero when findings exist.
6. Added regression coverage.

Status:

- Repo mechanism: closed.

## Gap 86

Gap: Engineering quality lacks CI, release, contribution, governance, and security scaffolding.

Implemented:

1. Added `scripts/ci.sh`.
2. Added `CONTRIBUTING.md`.
3. Added `GOVERNANCE.md`.
4. Added `SECURITY.md`.
5. Added `docs/release.md`.

Status:

- Repo mechanism: closed for baseline project maturity scaffolding.
- Signed releases, SBOM, vulnerability scanning, and long-term support policy remain future release operations.
