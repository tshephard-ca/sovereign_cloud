# Core Technology Gap Register

This document lists the remaining gaps that limit `estate-triage` from being a defensible core technology with durable business impact.

The current implementation is a strong deterministic assessment kernel and data workflow. It already has canonical evidence, provenance, identity states, feature traces, policy traces, redaction, fingerprints, synthetic real-world-like bundle generation, and multiple ranking modes. The gaps below are the work required to move from a useful local triage engine into a mature technology platform that can survive messy field data, repeatable partner workflows, governance scrutiny, and commercial-scale adoption.

## Executive Gap Summary

1. The core engine is deterministic and explainable, but the scoring policy is not yet calibrated against enough real-world assessments.
2. The synthetic generator covers important scenarios, but it is not statistically grounded in observed production estate distributions.
3. Identity resolution is auditable, but still too narrow for estates with renames, duplicate records, partial identifiers, and multi-source conflicts.
4. Validation finds problems, but does not yet produce a readiness grade, remediation plan, or data-request checklist.
5. The output identifies review candidates, but does not yet prove business impact through accepted-findings tracking, time-saved metrics, or workflow conversion metrics.
6. The policy engine is versioned, but policy packs lack lifecycle governance, compatibility tests, expected-outcome regression suites, and change-impact reports.
7. Privacy is strong for local redaction, but field-level privacy policy, validation-output redaction, and enterprise review controls remain incomplete.
8. The tool is usable as a CLI and library, but packaging, release, CI, performance benchmarks, and operational maturity are still early.

## Gap Severity Definitions

- `Core blocker`: limits defensibility of the technology itself.
- `High`: limits adoption in real field assessments or partner workflows.
- `Medium`: limits scale, automation, or repeatability.
- `Later`: useful once the core workflow is proven.

## 1. Real-World Data And Corpus Gaps

1. `Core blocker`: No sanitized field corpus exists yet. The generator is synthetic-realistic, but defensible scoring needs a growing corpus of sanitized real assessment shapes.
2. `Core blocker`: The generator is scenario-driven, not distribution-driven. It intentionally creates cases, but does not model the frequency of those cases in real estates.
3. `Core blocker`: There is no estate-size distribution model. Small, medium, large, and very large estates should have different workload counts, duplication rates, backup coverage rates, and utilization coverage rates.
4. `High`: The generator does not model multi-source inventory imports from more than one infrastructure inventory export.
5. `High`: The generator does not model multiple backup exports for the same estate.
6. `High`: The generator does not model partial exports, stale exports, or exports captured on different dates.
7. `High`: There is no longitudinal corpus. The engine cannot yet show how findings change across two or more assessment runs.
8. `High`: There is no feedback-labeled corpus where a human marks findings as accepted, rejected, needs-more-data, duplicate, or wrong-motion.
9. `High`: There is no corpus stratified by industry, organization size, regulatory pressure, operating model, or maturity level.
10. `Medium`: The corpus does not include enough malformed CSV cases: broken quoting, embedded delimiters, byte-order marks, irregular line endings, blank trailing columns, or duplicate headers.
11. `Medium`: The corpus does not include broad localization: non-English headers, decimal commas, local date formats, localized power-state strings, or localized unknown/null values.
12. `Medium`: The corpus does not include broad unit variation across MiB, GiB, TiB, MB, GB, TB, and unitless values in the same file.
13. `Medium`: The corpus does not include intentionally contradictory records, such as backup rows newer than inventory rows, in-use storage greater than provisioned storage, or utilization windows outside assessment dates.
14. `Medium`: The corpus does not include very sparse estates where only workload name and backup size exist.
15. `Medium`: The corpus does not include very rich estates with complete ownership, app, environment, protection, and utilization metadata.
16. `Medium`: The corpus does not include high-churn estates with many renamed, cloned, deleted, or restored workloads.
17. `Medium`: The corpus does not include backup-only records caused by decommissioned workloads.
18. `Medium`: The corpus does not include inventory-only records caused by new workloads that have not entered backup policy.
19. `Medium`: The corpus does not include extreme outliers: very large memory, very high CPU, tiny disk, huge backup footprint, very high restore point count, or long snapshot chains.
20. `Later`: The corpus does not include controlled benchmark cases for parser performance at 10k, 100k, and 1M rows.

## 2. Input Data Readiness Gaps

1. `Core blocker`: Validation does not produce a single data-readiness grade that tells a field user whether the assessment is reliable enough to present.
2. `Core blocker`: Validation does not produce a structured remediation plan for missing or bad columns.
3. `High`: Validation does not estimate matchability before analysis, such as expected UUID match rate, name-only rate, and likely duplicate rate.
4. `High`: Validation does not assign business severity to data problems. Missing backup size and missing optional notes are not equally important.
5. `High`: Validation does not identify stale input files from manifest timestamps or embedded export timestamps.
6. `High`: Validation does not detect whether inventory, backup, and utilization windows are aligned.
7. `High`: Validation does not produce a data-request checklist for the partner or customer contact.
8. `High`: Validation does not provide field-level confidence scores for mapped columns.
9. `Medium`: Validation does not show example parsed values for every mapped column.
10. `Medium`: Validation does not detect columns that are mapped but mostly blank.
11. `Medium`: Validation does not detect columns with mixed units or mixed date formats.
12. `Medium`: Validation does not detect low-cardinality fields that are probably incorrectly mapped.
13. `Medium`: Validation does not detect high-cardinality fields that are probably identifiers rather than categories.
14. `Medium`: Validation does not detect impossible or suspicious numeric ranges across every canonical field.
15. `Medium`: Validation does not detect duplicate workload rows as a first-class finding.
16. `Medium`: Validation does not detect duplicate backup rows as a severity-ranked condition beyond candidate ambiguity.
17. `Medium`: Validation does not detect if a mapping file references columns absent from the input.
18. `Medium`: Validation does not generate automatic mapping alternatives with confidence.
19. `Medium`: Validation does not preserve a human approval record for mapping decisions.
20. `Later`: Validation does not generate an intake scorecard suitable for a pre-assessment kickoff call.

## 3. Identity Resolution Gaps

1. `Core blocker`: Identity resolution is based primarily on UUID and normalized name, not a fuller identity graph.
2. `Core blocker`: There is no user-supplied identity override file to resolve known conflicts without editing source CSVs.
3. `High`: Historical names are not supported, so renamed workloads can split across inventory, backup, and utilization records.
4. `High`: Fuzzy matching is not supported for controlled cases such as punctuation differences, suffix differences, domain prefixes, or case variations beyond normalization.
5. `High`: Identity does not use context such as datacenter, cluster, host, folder, environment, backup job, or repository to resolve ambiguous names.
6. `High`: Duplicate inventory rows are not modeled as a first-class identity condition.
7. `High`: Duplicate UUIDs are not modeled as a first-class identity condition.
8. `High`: Clone/template relationships are not modeled.
9. `Medium`: Workload aliases are not supported.
10. `Medium`: Identity confidence is not decomposed into identifier confidence, contextual confidence, and conflict confidence.
11. `Medium`: Unmatched backup rows are not categorized by likely cause.
12. `Medium`: Identity conflicts are surfaced, but there is no remediation workflow.
13. `Medium`: Identity traces are useful for engineers but not yet summarized for field review.
14. `Medium`: There is no stable identity graph export for downstream tools.
15. `Later`: There is no incremental identity reconciliation across repeated assessment runs.

## 4. Feature Engineering Gaps

1. `Core blocker`: Feature completeness is narrow. The current features are enough for MVP triage but not enough for durable core differentiation.
2. `High`: There are no time-windowed utilization features beyond normalized aggregate utilization.
3. `High`: There are no workload volatility features across multiple backup or inventory snapshots.
4. `High`: There are no application-context features such as environment, owner, business service, dependency group, or lifecycle state.
5. `High`: There are no protection-policy fit features comparing backup policy, retention, restore point age, and stated RPO/RTO expectations.
6. `High`: There are no storage-efficiency features separating provisioned, used, consumed, snapshot, backup, and change-rate effects.
7. `High`: There are no data-quality-derived features that penalize or qualify scoring based on evidence weakness.
8. `Medium`: Feature confidence is not separated from final recommendation confidence.
9. `Medium`: Feature traces are present but not grouped into field-friendly explanations.
10. `Medium`: Feature version migration is not implemented for future changes.
11. `Medium`: Feature calculators are not performance-benchmarked at large row counts.
12. `Medium`: There are no feature-level property tests for edge cases such as zero values, missing values, negative values, and extreme values.
13. `Medium`: There is no feature store or cache for repeated assessments.
14. `Later`: There is no plug-in feature API for third-party feature packs.
15. `Later`: There is no feature-impact report explaining which features most often drive decisions across an estate.

## 5. Policy And Scoring Gaps

1. `Core blocker`: The default scoring policy is heuristic and not calibrated against accepted field outcomes.
2. `Core blocker`: Scores are not proven comparable across motions. A score of 80 in migration does not necessarily mean the same opportunity strength as 80 in DR review.
3. `High`: Global ranking can bury commercially important right-sizing or archive findings behind high-scoring migration findings.
4. `High`: Policy packs do not have expected-outcome regression assertions against a golden corpus.
5. `High`: Policy change-impact reporting is not implemented.
6. `High`: There is no policy compatibility matrix for schema versions, feature versions, and assessment versions.
7. `High`: There is no policy approval workflow.
8. `High`: There is no policy pack library for different assessment objectives.
9. `High`: There is no field-tuned threshold guidance based on estate size or data completeness.
10. `Medium`: Confidence is coarse: high, medium, low.
11. `Medium`: There is no separate confidence for identity, feature quality, policy fit, and final presentation.
12. `Medium`: Scoring does not currently penalize excessive missing evidence consistently across all motions.
13. `Medium`: Blocking flags do not yet have severity levels.
14. `Medium`: Missing-evidence requests are not ranked by expected impact on confidence.
15. `Medium`: Archive scoring does not yet use last powered-on or last-seen data when available.
16. `Medium`: DR tier scoring does not yet compare observed evidence against declared RPO/RTO policy.
17. `Medium`: Migration scoring does not yet consider dependency complexity.
18. `Medium`: Right-sizing scoring does not yet distinguish sustained low utilization from short observation windows.
19. `Medium`: Policy results are deterministic, but there is no formal explainability contract for each motion.
20. `Later`: There is no simulation mode for threshold sensitivity analysis.

## 6. Output And Business Workflow Gaps

1. `Core blocker`: The tool does not yet measure whether generated findings are accepted, rejected, or converted into next-step work.
2. `Core blocker`: There is no business-impact ledger that tracks time saved, assessment acceleration, additional qualified opportunities, or avoided low-value pursuits.
3. `High`: The output does not produce a field-ready discovery-call plan.
4. `High`: The output does not generate per-motion work queues with owners, evidence requested, and next action.
5. `High`: The output does not group findings by application, owner, environment, or business service.
6. `High`: The output does not identify duplicates or clusters of related findings that should be discussed together.
7. `High`: The output does not produce a stakeholder-safe executive summary distinct from the technical assessment JSON.
8. `High`: The output does not clearly separate "strong candidate" from "needs more data" across every motion.
9. `Medium`: Summary JSON reports counts but not outcome quality, readiness, or business workflow balance.
10. `Medium`: The CSV output is intentionally flat, but there is no richer Markdown or structured report renderer for human review.
11. `Medium`: There is no automatic checklist of which missing fields would improve which motions.
12. `Medium`: There is no evidence packet per workload.
13. `Medium`: There is no side-by-side comparison of global ranking versus per-motion ranking.
14. `Medium`: There is no explicit "do not present" filter for low-confidence or conflict-heavy findings.
15. `Medium`: There is no export tailored for task tracking systems.
16. `Medium`: There is no workflow state model for triage findings.
17. `Medium`: There is no batch comparison between assessments.
18. `Later`: There is no one-page handoff pack for a technical workshop.
19. `Later`: There is no template library for partner-specific review motions.
20. `Later`: There is no controlled natural-language report generation from rule traces.

## 7. Business Value And Commercial Defensibility Gaps

1. `Core blocker`: The product does not yet prove that it creates more qualified assessment conversations than manual spreadsheet triage.
2. `Core blocker`: It does not yet prove that its recommendations are accepted by field practitioners at a high enough rate.
3. `High`: There is no baseline comparison against manual triage time.
4. `High`: There is no measurement of false positives by motion.
5. `High`: There is no measurement of false negatives because unknown missed opportunities are not tracked.
6. `High`: There is no conversion funnel from input bundle to validated assessment to accepted review candidate to completed next step.
7. `High`: There is no partner enablement workflow that shows how to use findings in a sales-engineering conversation.
8. `High`: There is no business-value taxonomy beyond the four motions.
9. `Medium`: There is no outcome vocabulary for why a finding was rejected.
10. `Medium`: There is no repeat-assessment metric showing whether data quality improved after a feedback cycle.
11. `Medium`: There is no retained benchmark set showing policy accuracy over time.
12. `Medium`: There is no case-study-safe sanitized narrative format.
13. `Medium`: There is no product analytics design, even local-only, to measure usage and value without telemetry.
14. `Medium`: There is no documented buyer/user split, such as partner engineer, pre-sales architect, operations owner, or assessment manager.
15. `Later`: There is no pricing or packaging strategy, intentionally outside the MVP but necessary for commercial impact.

## 8. Privacy, Security, And Governance Gaps

1. `Core blocker`: Validation JSON is not automatically redacted under the same privacy profile as assessment JSON.
2. `High`: Privacy profiles are fixed and not user-configurable at field level.
3. `High`: There is no privacy review report showing exactly which fields were redacted, hashed, preserved, or dropped.
4. `High`: Fingerprints include column names, which may be sensitive in some organizations.
5. `High`: Strict redaction preserves row numbers and column names, which may still be sensitive in unusual cases.
6. `High`: There is no reversible local alias map for internal use by an authorized team.
7. `Medium`: There is no redaction test harness that scans every output artifact produced by a bundle command.
8. `Medium`: There is no configurable salt policy.
9. `Medium`: There is no secret-handling policy because the tool should not need secrets, but accidental secret detection in inputs is not implemented.
10. `Medium`: There is no security threat model document.
11. `Medium`: There is no supply-chain hardening beyond minimal dependencies.
12. `Medium`: There is no signed-release process.
13. `Medium`: There is no software bill of materials generation.
14. `Later`: There is no formal privacy impact assessment template.
15. `Later`: There is no compliance mapping for regulated environments.

## 9. Adapter And Integration Gaps

1. `Core blocker`: There is no robust schema-mapper workflow for arbitrary exports beyond starter mapping files.
2. `High`: XLSX input is not implemented.
3. `High`: Multi-sheet workbook handling is not implemented.
4. `High`: Multiple inventory sources in one bundle are not supported as a first-class workflow.
5. `High`: Multiple backup sources in one bundle are not supported as a first-class workflow.
6. `High`: Mapping recommendations are not learned or refined from approved mappings.
7. `High`: Adapter tests do not cover enough messy export shapes.
8. `Medium`: There is no adapter compatibility test suite.
9. `Medium`: There is no canonical adapter metadata describing supported columns, quality, and limitations.
10. `Medium`: There is no schema drift detector between repeated exports.
11. `Medium`: There is no input preview command for mapped canonical records.
12. `Medium`: There is no interactive mapping assistant.
13. `Medium`: There is no official extension template for community adapters.
14. `Later`: There are no optional source-specific CSV mappers packaged as separate extensions.
15. `Later`: There is no controlled import from local databases or offline inventory snapshots.

## 10. Engineering Quality And Release Gaps

1. `Core blocker`: No CI workflow is committed.
2. `High`: No release workflow is committed.
3. `High`: No type-checking configuration is committed.
4. `High`: No linting or formatting configuration is committed.
5. `High`: No performance benchmark suite exists.
6. `High`: No property-based tests exist for parsers, identity, features, and scoring.
7. `High`: No fuzz tests exist for malformed CSV input.
8. `High`: No mutation testing exists for policy logic.
9. `Medium`: No JSON Schema artifacts are generated for public contracts.
10. `Medium`: No contract-compatibility tests exist across schema versions.
11. `Medium`: No CLI snapshot tests exist for help text and error behavior.
12. `Medium`: No packaging test verifies installation in a clean environment.
13. `Medium`: No dependency vulnerability scan is configured.
14. `Medium`: No benchmark thresholds prevent performance regressions.
15. `Medium`: No large-file memory-use tests exist.
16. `Medium`: No golden-output checks are enforced for generated bundles.
17. `Medium`: No documentation build check exists.
18. `Medium`: No contribution guidelines exist.
19. `Medium`: No governance model exists for accepting policy or adapter changes.
20. `Later`: No long-term support policy exists for public schema versions.

## 11. Product Surface Gaps

1. `High`: The CLI has many useful commands, but there is no guided workflow command that runs intake, validation, analysis, redaction, and summary in one opinionated sequence.
2. `High`: Error messages are clear for strict failures, but not yet consistently actionable for every data-quality condition.
3. `High`: There is no command that compares two assessment bundles.
4. `High`: There is no command that prints the most important missing evidence to request next.
5. `Medium`: There is no command that previews the top findings without writing output files.
6. `Medium`: There is no command that explains one workload in detail.
7. `Medium`: There is no command that lists policy thresholds with descriptions and business meaning.
8. `Medium`: There is no command that validates a policy against expected outcomes.
9. `Medium`: There is no command that exports a compact handoff bundle.
10. `Medium`: There is no structured exit-code contract for automation.
11. `Medium`: There is no shell-completion documentation.
12. `Medium`: There is no example showing a full bundle lifecycle from raw inputs to sanitized corpus.
13. `Later`: There is no terminal user interface for mapping review.
14. `Later`: There is no local desktop wrapper.
15. `Later`: There is no web UI, intentionally out of scope unless the kernel becomes embedded in a larger product.

## 12. Documentation And Enablement Gaps

1. `High`: Documentation explains what the tool does, but not enough about how to run a real assessment engagement.
2. `High`: There is no field playbook for each motion.
3. `High`: There is no interpretation guide for confidence, blocking flags, and missing evidence.
4. `High`: There is no decision guide for choosing global versus per-motion ranking.
5. `High`: There is no mapper authoring guide with examples of good and bad mappings.
6. `Medium`: There is no troubleshooting guide.
7. `Medium`: There is no FAQ for data honesty boundaries.
8. `Medium`: There is no glossary of canonical fields.
9. `Medium`: There is no architecture decision record series.
10. `Medium`: There is no public schema documentation generated from code.
11. `Medium`: There is no policy authoring guide.
12. `Medium`: There is no privacy guide explaining redaction tradeoffs.
13. `Medium`: There is no partner handoff guide.
14. `Later`: There is no training dataset for workshops.
15. `Later`: There are no tutorial videos or sample walkthrough scripts.

## 13. Limits Of The Current Real-World Data Generator

1. `High`: It validates coverage, not truth. The generator proves the engine handles scenarios; it does not prove the scenarios occur at realistic rates.
2. `High`: It does not generate business context fields such as owner, service, environment, cost center, compliance class, or lifecycle owner.
3. `High`: It does not generate dependency topology.
4. `High`: It does not generate time-series utilization.
5. `High`: It does not generate repeated assessments over time.
6. `High`: It does not generate source-export timestamps that can be used to test stale-input logic.
7. `Medium`: It does not generate enough malformed records.
8. `Medium`: It does not generate enough localization cases.
9. `Medium`: It does not generate a configurable estate profile.
10. `Medium`: It does not generate workloads where the right answer is intentionally "do not recommend any motion."
11. `Medium`: It does not generate complete ownership and approval workflows.
12. `Medium`: It does not generate feedback outcomes for scoring calibration.
13. `Medium`: It does not generate controlled false-positive and false-negative cases.
14. `Medium`: It does not generate multiple policy-pack expected results.
15. `Later`: It does not generate a synthetic organization narrative for demonstration packs.

## 14. Gaps Specific To Business Impact Claims

1. `Core blocker`: The project cannot yet credibly claim quantified business impact because it lacks outcome data.
2. `Core blocker`: The project cannot yet claim improved assessment conversion because there is no conversion tracking.
3. `High`: It can claim faster triage only as a hypothesis until benchmarked against manual work.
4. `High`: It can claim explainability, but not field acceptance, until accepted-findings data exists.
5. `High`: It can claim local privacy design, but not enterprise privacy readiness, until output-wide privacy validation is complete.
6. `High`: It can claim deterministic scoring, but not scoring correctness, until calibrated against reviewed assessments.
7. `Medium`: It can claim partner-distributable utility, but not partner program readiness, until enablement material and release discipline exist.
8. `Medium`: It can claim extensibility, but not ecosystem readiness, until adapter and policy extension contracts are documented and tested.
9. `Medium`: It can claim auditability, but not audit-grade governance, until schema artifacts, signed releases, and change logs exist.
10. `Later`: It can claim product potential, but not category leadership, until a distinct data moat or workflow moat is built.

## 15. Highest-Leverage Fixes

1. Build a sanitized golden corpus pipeline with expected outcome assertions.
2. Add bundle readiness scoring and a missing-evidence remediation checklist.
3. Add policy-pack regression tests and policy change-impact reporting.
4. Add accepted/rejected feedback outcomes and use them to evaluate policy quality.
5. Add richer identity resolution with override files, historical names, context scoring, and duplicate UUID handling.
6. Add a guided assessment workflow command that produces validation, analysis, redaction, summary, and handoff artifacts.
7. Add field-ready output: per-motion work queues, discovery-call checklist, and executive summary.
8. Add CI, type checking, linting, JSON Schema artifacts, performance benchmarks, and release automation.
9. Extend the real-world generator into configurable estate profiles with malformed data, time variance, feedback outcomes, and expected policy results.
10. Document the field playbook, ranking strategy, privacy model, policy authoring model, and evidence contract.

## Conclusion

The repo has crossed the line from a report generator into an early deterministic assessment kernel. The remaining gaps are mostly about proof, scale, governance, workflow, and data advantage.

The most important product question is no longer "can it score two CSV files?" It can. The next question is whether it can repeatedly turn messy local exports into trusted, accepted, and measurable field decisions. That requires real corpus development, feedback loops, policy governance, stronger identity, assessment-readiness scoring, and business workflow artifacts.
