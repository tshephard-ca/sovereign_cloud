# Generated Real-World Data Validation

This document records the validation pass for the deterministic real-world-like data generator.

## Commands Run

```bash
PYTHONPATH=src python3 -m estate_triage.cli generate-real-world-data \
  --output /tmp/estate-generated-bundle \
  --overwrite

PYTHONPATH=src python3 -m estate_triage.cli analyze-bundle \
  /tmp/estate-generated-bundle \
  --top-n 50

PYTHONPATH=src python3 -m estate_triage.cli validate \
  --kind inventory \
  --input /tmp/estate-generated-bundle/inputs/inventory.csv \
  --mapping /tmp/estate-generated-bundle/mappings/inventory-map.yml \
  --output-json /tmp/estate-generated-bundle/outputs/inventory-validation.json

PYTHONPATH=src python3 -m estate_triage.cli validate \
  --kind backup \
  --input /tmp/estate-generated-bundle/inputs/backup_export.csv \
  --mapping /tmp/estate-generated-bundle/mappings/backup-map.yml \
  --output-json /tmp/estate-generated-bundle/outputs/backup-validation.json

PYTHONPATH=src python3 -m estate_triage.cli validate \
  --kind utilization \
  --input /tmp/estate-generated-bundle/inputs/utilization.csv \
  --mapping /tmp/estate-generated-bundle/mappings/utilization-map.yml \
  --output-json /tmp/estate-generated-bundle/outputs/utilization-validation.json
```

## Generated Input Coverage

The generated bundle contains:

- inventory rows: `94`
- backup rows: `92`
- utilization rows: `34`

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

The generator also adds backup-only unmatched rows.

Input ranges:

- in-use storage: `0` to `1,330,000` MiB
- CPU allocation: `2` to `16`
- memory allocation: `4,096` to `65,536` MiB
- backup footprint: `30,500` to `5,320,000` MiB
- restore points: `3` to `57`
- CPU p95 utilization: `4` to `35` percent
- memory p95 utilization: `25` to `65` percent

Input distribution:

- powered on: `74`
- powered off: `12`
- blank power state: `8`
- known OS: `82`
- unknown OS: `12`

Input validation:

- inventory validation findings: `0`
- backup validation findings: `2`
- utilization validation findings: `0`

The two backup findings are intentional ambiguous date cases.

## Output Coverage

Identity outcomes:

| Status | Count |
| --- | ---: |
| RESOLVED | 70 |
| UNMATCHED | 13 |
| PROBABLE | 5 |
| CONFLICTED | 3 |
| DUPLICATE_CANDIDATES | 3 |

Confidence distribution:

| Confidence | Count |
| --- | ---: |
| high | 64 |
| medium | 5 |
| low | 25 |

Primary motion distribution across all generated workloads:

| Motion | Count |
| --- | ---: |
| MIGRATION_REVIEW | 52 |
| RIGHTSIZING_REVIEW | 18 |
| ARCHIVE_REVIEW | 12 |
| DR_TIER_REVIEW | 12 |

Scenario-to-motion behavior:

- `migration_easy` -> `MIGRATION_REVIEW`
- `dr_large_low_change` -> `DR_TIER_REVIEW`
- `archive_powered_off_stale` -> `ARCHIVE_REVIEW`
- `rightsizing_util_backed` -> `RIGHTSIZING_REVIEW`
- `allocation_only_rightsizing` -> `RIGHTSIZING_REVIEW`
- `name_only_match` -> `MIGRATION_REVIEW` with name-match confidence behavior
- `uuid_name_conflict` -> conflict trace with UUID preferred
- `duplicate_name_candidates` -> duplicate-candidate trace
- `missing_storage_used` -> missing storage blocking behavior
- `ambiguous_backup_date` -> parse warnings and missing restore-point behavior

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

| Blocking Flag | Count |
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

Top missing-evidence requests:

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

## Business Impact Validation

The generated data exercises the main business stories:

- migration review: powered-on, recently protected, low-change, small-footprint workloads
- archive review: powered-off, stale-protected, unknown-OS workloads
- right-sizing review: utilization-backed and allocation-only variants
- DR tier review: large backup footprint, low change rate, high backup-to-used ratio, many restore points
- assessment intake: missing storage, missing backup match, missing utilization, ambiguous dates
- trust workflow: UUID/name conflicts, duplicate candidates, unmatched backup rows, name-only matches
- partner handoff: strict redaction, fingerprints, validation reports, feedback file, sanitized corpus case

The output is commercially useful because it produces:

- explainable review candidates
- confidence and blocking flags
- data-quality findings
- missing-evidence requests
- redacted shareable assessment JSON
- reproducible input fingerprints

## Ranking Observation

With global ranking, the generated top 50 contains:

- `MIGRATION_REVIEW`: 35
- `DR_TIER_REVIEW`: 12
- `ARCHIVE_REVIEW`: 3
- `RIGHTSIZING_REVIEW`: 0

This is explainable because migration candidates score very high under the default policy. It is also a business gap: right-sizing findings exist but are buried in global ranking.

With `--ranking-mode per_motion --top-n 10`, output contains:

- `MIGRATION_REVIEW`: 10
- `ARCHIVE_REVIEW`: 10
- `RIGHTSIZING_REVIEW`: 10
- `DR_TIER_REVIEW`: 10

The current default is `balanced`, which keeps `top_n` as a total row cap while round-robin selecting across motions. `per_motion` remains useful when the user intentionally wants top N from each motion.

## Privacy Validation

Strict redaction was checked against generated outputs. No generated workload names, UUIDs, backup job names, repository names, or source input paths were found in the redacted assessment JSON.

Strict mode still preserves row numbers, column names, numeric metrics, scores, reason codes, and finding codes. That is intentional for auditability.

## Remaining Gaps

### Generator Realism Gaps

1. The generator is deterministic and scenario-driven, not statistically derived from real estate distributions.
2. It does not model very large estates with tens of thousands of workloads.
3. It does not model multi-file inventory exports from multiple infrastructure sources.
4. Edge-case mode now generates malformed CSV structure, embedded newlines, duplicate headers, irregular line endings, extra columns, and missing columns.
5. It does not generate non-comma delimiters.
6. Edge-case mode now generates localized inventory and backup headers.
7. Edge-case mode now generates localized decimal-comma numeric formats and mixed storage units.
8. Edge-case mode now generates an unambiguous dotted local date in addition to ISO and ambiguous slash-date coverage.
9. Duplicate inventory UUIDs are now detected by identity resolution, but the generator does not yet emit a dedicated duplicate-inventory scenario.
10. Duplicate backup UUID and name candidates are severity-ranked; generated duplicate name candidates are covered.
11. It does not generate historical rename chains.
12. It does not generate multi-tenant/project/account hierarchy.
13. It does not generate application dependency or topology data.
14. It does not generate owner, department, environment, or business-service fields.
15. It does not generate compliance, retention class, legal hold, or data classification fields.
16. It does not generate backup failures, job disabled states, repository capacity, or backup copy tiers.
17. It does not generate partial utilization windows with sparse sampling except through sample-count variation.
18. It does not generate time-series utilization, only normalized aggregate utilization rows.
19. It now generates contradictory, sparse, rich-context, and extreme-outlier rows, but does not model their real field frequencies.
20. It does not generate seasonal or batch workload patterns.
20. It does not generate workloads whose utilization contradicts allocation in nuanced ways.
21. It does not generate storage unit variety in every supported suffix format.
22. It does not generate negative values except the adapter can flag them if present.
23. It does not generate zero backup sizes.
24. It does not generate extremely high snapshot chains.
25. It does not generate host/cluster/datacenter conflicts.

### Input Validation Gaps

1. Validation reports identify missing recommended fields but do not assign a data-readiness score.
2. Validation does not yet check plausible ranges for every numeric field.
3. Validation does not flag unusually high CPU, memory, storage, or backup values as outliers.
4. Validation does not detect stale inventory exports based on export timestamp.
5. Validation does not detect mismatched row counts across sources as a severity level.
6. Validation does not summarize matchability before full analysis.
7. Validation does not provide sample parsed values for mapper review.
8. Validation does not yet recommend exact mapping changes.
9. Validation does not classify warnings by business impact.
10. Validation does not currently emit a single bundle-level readiness grade.

### Output Validation Gaps

1. There is no automated business-impact score for an assessment.
2. There is no built-in check that every generated scenario appears in the ranked CSV.
3. Global ranking can hide useful lower-scoring motions.
4. The summary reports only counts, not whether output is balanced for a sales workflow.
5. Data-quality findings are counted but not grouped by severity in the summary.
6. Missing-evidence requests are row-level but not aggregated into a recommended data-request checklist.
7. Confidence is still coarse: high, medium, low.
8. There is no separate identity confidence, feature confidence, policy confidence, and output confidence.
9. Rule traces exist but are verbose and not summarized for business users.
10. There is no acceptance/false-positive tracking tied back to specific rule IDs.

### Policy And Scoring Gaps

1. Default scoring is still heuristic and uncalibrated.
2. Motion scores are not guaranteed to be comparable across motions.
3. Migration scoring dominates global ranking under many realistic conditions.
4. Right-sizing can score lower than migration even when utilization evidence is strong.
5. Archive scoring does not consider last powered-on or last-seen evidence yet.
6. DR tier scoring does not consider actual RPO/RTO policy fit.
7. Policy packs are loadable but not yet governed by a compatibility matrix.
8. `test-policy` currently verifies loadability against corpus cases, not expected outcome assertions.
9. Policy change impact reports are not implemented.
10. There is no library of alternative policy packs.

### Identity Resolution Gaps

1. Identity resolution uses UUID and normalized name but not host, cluster, datacenter, or context scoring.
2. Name-only matching does not support fuzzy or tokenized matching.
3. Historical names are not supported.
4. Duplicate inventory rows are not explicitly resolved.
5. Multi-source identity graph behavior is still basic.
6. Conflicts are surfaced, but there is no remediation workflow.
7. Unmatched backup rows are summarized but not categorized by likely cause.
8. There is no user-supplied identity override file.

### Privacy And Sharing Gaps

1. Strict redaction preserves row numbers and column names, which may still be sensitive in some environments.
2. Privacy profiles are fixed; there is no custom field-level redaction policy file.
3. Salt generation is simple and local but not integrated with secret-management workflows.
4. Fingerprints include column names, which may be sensitive for some users.
5. Validation JSON is not automatically redacted by privacy mode.
6. Redaction does not yet support reversible local alias maps for internal teams.

### Business Impact Gaps

1. The tool does not measure time saved.
2. The tool does not measure accepted versus rejected findings beyond local feedback files.
3. Feedback is summarized but not used to evaluate policy effectiveness.
4. There is no assessment conversion metric.
5. There is no discovery-call checklist generated from missing evidence.
6. There is no partner enablement package with workflow guidance.
7. There is no benchmark against manual spreadsheet triage.
8. There is no field validation from real partner assessments.
9. There is no documented ROI model, intentionally no pricing model.
10. There is no packaged release process or CI badge to establish operational maturity.

### Engineering Maturity Gaps

1. No CI workflow is included.
2. No package publishing workflow is included.
3. No semantic-versioning policy for public schemas is documented beyond version constants.
4. No JSON Schema files are committed as release artifacts.
5. No performance benchmark suite exists.
6. No mutation or property-based tests exist for parsers.
7. Targeted malformed CSV regression tests exist for generated edge-case fixtures, but no property-based fuzz test suite exists yet.
8. No type-checking configuration is included.
9. No linting configuration is included.
10. Generated example outputs are ignored, but generated corpus management is still manual.
