# Real-World Generator Audit

This audit records a fresh run of the deterministic real-world-like data generator and validates whether the generated input and output data provide useful coverage, realistic triage signals, and business-impact evidence.

Important boundary: this is synthetic-realistic data. It validates scenario coverage, parser behavior, scoring behavior, redaction, readiness reporting, and business workflow shape. It does not prove real-world frequency, field acceptance, or commercial conversion without a sanitized field corpus.

## Commands Run

```bash
PYTHONPATH=src python3 -m estate_triage.cli generate-real-world-data \
  --output /tmp/estate-real-world-audit-latest \
  --profile coverage \
  --overwrite

PYTHONPATH=src python3 -m estate_triage.cli validate-generator-profile \
  --profile-config /tmp/estate-real-world-audit-latest/generator-profile.yml

PYTHONPATH=src python3 -m estate_triage.cli validate-generator-profile \
  --profile-config /tmp/estate-real-world-audit-latest/generator-profile.yml \
  --require-field-derived

PYTHONPATH=src python3 -m estate_triage.cli validate \
  --kind inventory \
  --input /tmp/estate-real-world-audit-latest/inputs/inventory.csv \
  --mapping /tmp/estate-real-world-audit-latest/mappings/inventory-map.yml \
  --output-json /tmp/estate-real-world-audit-latest/outputs/inventory-validation.json

PYTHONPATH=src python3 -m estate_triage.cli validate \
  --kind backup \
  --input /tmp/estate-real-world-audit-latest/inputs/backup_export.csv \
  --mapping /tmp/estate-real-world-audit-latest/mappings/backup-map.yml \
  --output-json /tmp/estate-real-world-audit-latest/outputs/backup-validation.json

PYTHONPATH=src python3 -m estate_triage.cli validate \
  --kind utilization \
  --input /tmp/estate-real-world-audit-latest/inputs/utilization.csv \
  --mapping /tmp/estate-real-world-audit-latest/mappings/utilization-map.yml \
  --output-json /tmp/estate-real-world-audit-latest/outputs/utilization-validation.json

PYTHONPATH=src python3 -m estate_triage.cli analyze-bundle \
  /tmp/estate-real-world-audit-latest \
  --top-n 50 \
  --no-redact

PYTHONPATH=src python3 -m estate_triage.cli analyze-bundle \
  /tmp/estate-real-world-audit-latest \
  --top-n 10 \
  --ranking-mode per_motion

python3 -m pytest -q
```

Privacy scan:

```bash
rg -n "mig-app|gen-mig|job-|repo-|inputs/inventory.csv|inputs/backup_export.csv|inputs/utilization.csv" \
  /tmp/estate-real-world-audit-latest/outputs/assessment.json \
  /tmp/estate-real-world-audit-latest/outputs/validation.json
```

The privacy scan found no matches in the redacted assessment or validation artifacts.

Test result: `41 passed`.

## Generator Profile

The current run used the built-in `coverage` profile.

| Profile Field | Value |
| --- | --- |
| name | coverage |
| source | synthetic-coverage |
| description | Broad deterministic coverage profile for regression and workflow testing. |

The generator now supports multiple built-in profiles and custom `--profile-config` files. `validate-generator-profile` accepts this profile as structurally valid coverage data. `validate-generator-profile --require-field-derived` correctly rejects it because `synthetic-coverage` is not sanitized field-derived calibration.

That closes the hard-coded-distribution limitation and adds a field-calibration gate at the repo-mechanism level. It does not make the default profile statistically field-calibrated; that still requires sanitized field-derived profile data.

## Input Data Coverage

Generated row counts:

| Input | Rows |
| --- | ---: |
| Inventory | 94 |
| Backup | 92 |
| Utilization | 34 |

Scenario coverage:

| Scenario | Rows |
| --- | ---: |
| migration_easy | 24 |
| dr_large_low_change | 12 |
| archive_powered_off_stale | 12 |
| rightsizing_util_backed | 10 |
| allocation_only_rightsizing | 8 |
| snapshot_blocker | 6 |
| no_backup_match | 5 |
| name_only_match | 5 |
| missing_storage_used | 4 |
| uuid_name_conflict | 3 |
| duplicate_name_candidates | 3 |
| ambiguous_backup_date | 2 |

The generator also includes backup-only unmatched records.

Input value ranges:

| Field | Range |
| --- | ---: |
| CPU allocation | 2 to 16 |
| Memory allocation | 4,096 to 65,536 MiB |
| Provisioned storage | 153,600 to 2,660,000 MiB |
| In-use storage | 0 to 1,330,000 MiB |
| Backup footprint | 30,500 to 5,320,000 MiB |
| Restore points | 3 to 57 |
| Average daily change | 100 to 24,400 MiB |
| CPU p95 utilization | 4 to 35 percent |
| Memory p95 utilization | 25 to 65 percent |

Input categorical coverage:

| Field | Distribution |
| --- | --- |
| Power state | 74 powered on, 12 powered off, 8 blank |
| OS | 82 known generic OS, 12 unknown |

Input validation:

| Input | Recognized Rows | Findings | Readiness |
| --- | ---: | ---: | --- |
| Inventory | 94 of 94 | 0 | A, 100 |
| Backup | 92 of 92 | 2 | C, 74 |
| Utilization | 34 of 34 | 0 | A, 100 |

The backup readiness grade is intentionally lower because the generator includes two ambiguous restore-point dates. That is useful coverage because it proves the tool does not silently accept ambiguous dates.

## Input Realism Assessment

The generated inputs are appropriate for coverage testing because they include:

1. Clean inventory rows with complete identity and storage evidence.
2. Backup rows with recent restore points.
3. Backup rows with stale restore points.
4. Backup rows with large backup footprints.
5. Workloads with missing backup matches.
6. Backup-only unmatched rows.
7. UUID/name conflict cases.
8. Name-only match cases.
9. Duplicate name candidate cases.
10. Missing in-use storage cases.
11. Snapshot blocker cases.
12. Utilization-backed right-sizing cases.
13. Allocation-only right-sizing cases.
14. Ambiguous date parse cases.
15. Low-confidence and high-confidence paths.

The generated inputs are not yet realistic enough to represent field frequency or full enterprise messiness because they do not include enough malformed files, localization, duplicate UUIDs, historical renames, application context, ownership data, dependency data, export-age skew, or broad operating-system diversity.

## Output Coverage

Identity outcomes across all generated workloads:

| Identity Status | Count |
| --- | ---: |
| RESOLVED | 70 |
| UNMATCHED | 13 |
| PROBABLE | 5 |
| CONFLICTED | 3 |
| DUPLICATE_CANDIDATES | 3 |

Confidence distribution:

| Confidence | Count |
| --- | ---: |
| High | 64 |
| Medium | 5 |
| Low | 25 |

Primary motion coverage across all workloads:

| Motion | Count |
| --- | ---: |
| MIGRATION_REVIEW | 52 |
| ARCHIVE_REVIEW | 12 |
| RIGHTSIZING_REVIEW | 18 |
| DR_TIER_REVIEW | 12 |

Scenario-to-motion behavior:

| Scenario | Winning Motion |
| --- | --- |
| migration_easy | MIGRATION_REVIEW |
| dr_large_low_change | DR_TIER_REVIEW |
| archive_powered_off_stale | ARCHIVE_REVIEW |
| rightsizing_util_backed | RIGHTSIZING_REVIEW |
| allocation_only_rightsizing | RIGHTSIZING_REVIEW |
| snapshot_blocker | MIGRATION_REVIEW with snapshot blocking flag |
| no_backup_match | MIGRATION_REVIEW with no-backup blocking behavior |
| name_only_match | MIGRATION_REVIEW with name-only confidence behavior |
| missing_storage_used | MIGRATION_REVIEW with storage-used missing evidence |
| uuid_name_conflict | MIGRATION_REVIEW with conflict trace |
| duplicate_name_candidates | MIGRATION_REVIEW with duplicate-candidate trace |
| ambiguous_backup_date | MIGRATION_REVIEW with restore-point parse warning |

Average winning score:

| Motion | Average Score |
| --- | ---: |
| DR_TIER_REVIEW | 90.00 |
| MIGRATION_REVIEW | 82.31 |
| ARCHIVE_REVIEW | 80.00 |
| RIGHTSIZING_REVIEW | 51.11 |

Data-quality codes emitted:

| Code | Count |
| --- | ---: |
| UNMATCHED_INVENTORY | 13 |
| UUID_NAME_CONFLICT | 3 |
| DUPLICATE_NAME | 3 |
| DUPLICATE_NAME_CANDIDATES | 3 |
| PARSE_WARNING | 2 |
| UNMATCHED_BACKUP_ROWS | 1 |

Top blocking flags:

| Flag | Count |
| --- | ---: |
| MISSING_CHANGE_RATE | 17 |
| NO_BACKUP_MATCH | 13 |
| MISSING_BACKUP_SIZE | 13 |
| POWERED_OFF_NOT_MIGRATION_CANDIDATE | 12 |
| LOW_CONFIDENCE_RIGHTSIZING | 8 |
| NAME_MATCH_ONLY | 8 |
| SNAPSHOT_PRESENT | 6 |
| MISSING_STORAGE_USED | 4 |
| CONFLICTED | 3 |
| DUPLICATE_CANDIDATES | 3 |

Top missing evidence:

| Missing Evidence | Count |
| --- | ---: |
| change_rate_pct | 17 |
| latest_restore_point_utc | 15 |
| backup_total_mib | 13 |
| avg_daily_change_mib | 13 |
| restore_point_count | 13 |
| memory_usage_pct | 12 |
| cpu_usage_pct | 12 |
| os | 12 |
| power_state | 8 |
| in_use_mib | 4 |

Ranking comparison:

| Ranking Mode | Output Mix |
| --- | --- |
| global, top 50 | 35 migration, 12 DR, 3 archive, 0 right-sizing |
| per_motion, top 10 | 10 migration, 10 archive, 10 right-sizing, 10 DR |

The global top-50 behavior is deterministic and explainable, but it is not ideal for balanced sales-engineering workflow. Per-motion ranking is more appropriate when a user needs complete motion coverage.

## Output Realism And Business-Impact Assessment

The output is realistic enough for demo, regression, partner training, and workflow testing because it creates:

1. Migration candidates that are powered on, recently backed up, low-change, and small enough to investigate.
2. Archive review candidates that are powered off, stale, and unknown-OS without claiming they are unused.
3. Right-sizing review candidates split between utilization-backed and allocation-only signals.
4. DR tier review candidates with large backup footprint, low change rate, high backup-to-used ratio, and many restore points.
5. Blocking flags that prevent overconfident action.
6. Missing-evidence requests that tell a partner what to request next.
7. Identity confidence states that separate UUID matches, name matches, conflicts, duplicates, and unmatched records.
8. Data-readiness grades that expose whether source quality is presentation-ready.
9. Redacted outputs that can be shared without generated workload identifiers.

Business-impact validation:

1. It produces concrete review worklists, not generic reports.
2. It gives sales engineers four practical motions to discuss.
3. It identifies data gaps before a deeper assessment.
4. It prevents unsupported claims by using review language and blocking flags.
5. It supports handoff by preserving row-level provenance, reason codes, missing data, and confidence.
6. It demonstrates why per-motion ranking matters for balanced opportunity discovery.

Business-impact limitation:

The run validates that the tool can produce plausible and useful review candidates from synthetic-realistic exports. It does not prove actual business impact until real sanitized assessments show accepted findings, time saved, lower triage effort, improved conversion, or better assessment quality.

## Extensive Gap List

### Generator Coverage Gaps

1. The generator supports built-in and custom profiles, but the checked-in profiles are still synthetic and not statistically derived from real estates.
2. It does not model estate-size profiles for small, medium, large, and very large environments.
3. It does not model tens of thousands of workloads.
4. It does not create multiple inventory exports for one assessment.
5. It does not create multiple backup exports for one assessment.
6. It does not create repeated assessments over time.
7. It does not create stale inventory exports.
8. It does not create source exports captured on different dates.
9. It does not create partial exports where one source only covers part of the estate.
10. It does not create enough malformed CSV structure.
11. It does not create duplicate headers.
12. It does not create embedded delimiters and embedded newlines.
13. It does not create mixed encodings.
14. It does not create non-comma delimiters.
15. It does not create localized headers.
16. It does not create localized date strings beyond one ambiguous slash-date case.
17. It does not create localized numeric formats.
18. It does not create localized power-state values.
19. It does not create enough unit variation across storage fields.
20. It does not create negative numeric values.
21. It does not create impossible numeric combinations such as used storage greater than provisioned storage.
22. It does not create zero backup-size cases.
23. It does not create extremely high snapshot chains.
24. It does not create duplicate UUIDs.
25. It does not create duplicate inventory rows.
26. It does not create historical rename chains.
27. It does not create restored, cloned, or template-derived workload relationships.
28. It does not create enough OS diversity.
29. It does not create owner, department, cost center, service, application, or environment fields.
30. It does not create dependency or topology data.
31. It does not create compliance class, data classification, legal hold, or retention-class fields.
32. It does not create backup failure-state diversity.
33. It does not create disabled protection-policy cases.
34. It does not create repository capacity pressure.
35. It does not create backup-copy or offsite-copy evidence.
36. It does not create seasonal workload patterns.
37. It does not create batch workloads.
38. It does not create time-series utilization.
39. It does not create utilization windows with strong sampling gaps.
40. It does not create feedback outcomes for accepted and rejected findings.
41. It does not include a sanitized field-derived generator profile in the repository.
42. It does not include confidence intervals or observed frequency metadata for scenario ratios.
43. It does not model correlations between scenarios, such as stale protection being more common in powered-off workloads.

### Input Validation Gaps

1. Validation has readiness grades, but no estate-level readiness acceptance threshold.
2. Validation does not yet forecast matchability before full analysis.
3. Validation does not classify every warning by business impact.
4. Validation does not detect stale export dates.
5. Validation does not detect source-window misalignment.
6. Validation does not summarize whether backup and utilization coverage are adequate for the intended motion.
7. Validation does not show sample parsed values for each mapped column.
8. Validation does not detect mostly blank mapped columns.
9. Validation does not detect mixed units within one column.
10. Validation does not detect mixed date formats within one column.
11. Validation does not detect suspicious cardinality patterns.
12. Validation does not perform full plausible range checks for every numeric field.
13. Validation does not detect duplicate inventory rows as a dedicated finding.
14. Validation does not detect duplicate UUIDs as a dedicated finding.
15. Validation does not provide automated mapping alternatives.
16. Validation does not record human approval for mapping decisions.
17. Validation does not produce a kickoff-call scorecard.
18. Validation does not produce a source-owner checklist.
19. Validation does not compare actual columns with prior assessment columns.
20. Validation does not estimate how much confidence would improve if missing fields were supplied.

### Output And Ranking Gaps

1. Global ranking hides right-sizing in this generated run.
2. The default ranking mode may not match the desired business workflow.
3. Output does not include a balanced-coverage warning when a motion is absent from global output.
4. Output does not include a ranking-mode recommendation.
5. Output does not include a discovery-call checklist.
6. Output does not include per-motion owners or next actions.
7. Output does not include a stakeholder-safe executive summary.
8. Output does not include a "do not present" filter.
9. Output does not group related findings.
10. Output does not group workloads by app, service, owner, environment, or location.
11. Output does not create evidence packets per workload.
12. Output does not compare this assessment to a prior run.
13. Output does not measure accepted, rejected, or converted findings.
14. Output does not calculate time saved.
15. Output does not record whether missing evidence was later supplied.

### Policy And Scoring Gaps

1. Scores are still heuristic.
2. Scores are not calibrated against field-reviewed outcomes.
3. Scores are not proven comparable across motions.
4. Right-sizing scores are lower than migration and DR scores in the generated data.
5. Archive scoring does not fully use last-powered-on and last-seen evidence.
6. DR scoring does not compare observed evidence against declared RPO/RTO expectations.
7. Migration scoring does not account for dependency complexity.
8. Right-sizing scoring does not account for observation-window quality.
9. Missing evidence is not consistently weighted by expected impact.
10. Blocking flags do not have severity levels.
11. Confidence is still coarse.
12. Identity confidence, feature confidence, and policy confidence are not separated.
13. Policy change-impact reports are not implemented.
14. Policy compatibility matrices are not implemented.
15. Alternative policy packs are not yet included.
16. Threshold sensitivity analysis is not implemented.
17. Policy approval workflow is not implemented.
18. Accepted/rejected feedback does not yet tune or evaluate policies.
19. There is no field-calibrated score benchmark.
20. There is no false-negative benchmark.

### Identity Resolution Gaps

1. Identity resolution still relies mainly on UUID and normalized name.
2. There is no identity override file.
3. Historical names are not supported.
4. Controlled fuzzy matching is not supported.
5. Context-aware matching is not implemented.
6. Duplicate UUIDs are not first-class cases.
7. Duplicate inventory rows are not first-class cases.
8. Clone/template relationships are not modeled.
9. Workload aliases are not modeled.
10. Unmatched backup rows are not categorized by likely cause.
11. Identity conflict remediation workflow is not implemented.
12. Identity graph export is not implemented.
13. Incremental reconciliation across repeated assessments is not implemented.
14. Identity confidence is not decomposed.
15. Identity traces are not yet summarized for field users.

### Business Impact Gaps

1. There is no real accepted-finding dataset.
2. There is no rejected-finding dataset.
3. There is no false-positive measurement.
4. There is no false-negative measurement.
5. There is no manual-triage time benchmark.
6. There is no conversion funnel from assessment to next-step work.
7. There is no repeat-assessment improvement metric.
8. There is no partner enablement validation.
9. There is no business-value taxonomy beyond the four motions.
10. There is no structured rejection reason taxonomy.
11. There is no real-world outcome ledger.
12. There is no evidence that the generated ranking improves discovery quality in the field.
13. There is no field validation that the missing-evidence checklist changes customer behavior.
14. There is no proof that redacted output is sufficient for all sharing workflows.
15. There is no externally reviewed case-study format.

### Engineering And Product Gaps

1. CI workflow is not committed.
2. Release workflow is not committed.
3. Type checking is not configured.
4. Linting and formatting are not configured.
5. Performance benchmarks are not implemented.
6. Large-file memory tests are not implemented.
7. Property-based parser tests are not implemented.
8. Fuzz tests are not implemented.
9. Mutation tests for policy logic are not implemented.
10. JSON Schema release artifacts are not generated.
11. Contract compatibility tests are not implemented.
12. CLI snapshot tests are limited.
13. Clean-install packaging tests are not implemented.
14. Dependency scanning is not configured.
15. Documentation build checks are not configured.
16. Contribution guidelines are not present.
17. Governance for policy and adapter changes is not defined.
18. Guided end-to-end workflow command is not implemented.
19. Explain-one-workload command is not implemented.
20. Assessment comparison command is not implemented.

## Audit Conclusion

The generator creates appropriate synthetic data for full MVP coverage. The input data validates cleanly except for intentional ambiguous date cases, and the output covers all four motions with useful reason codes, blockers, missing evidence, confidence levels, and identity states.

The output is realistic enough to support demos, tests, training, and product workflow design. It is not enough to claim field-proven business impact. The next step toward defensible core technology is a sanitized real assessment corpus with expected outcomes, accepted/rejected finding labels, field-derived generator profiles, and repeatable policy-quality measurement.
