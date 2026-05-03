# Generator Profile Calibration

The real-world generator supports deterministic synthetic profiles for testing and sanitized field-derived profiles for calibration.

This distinction matters. A synthetic profile can prove coverage. It cannot prove real-world frequency or business impact. A field-derived profile must come from sanitized assessment evidence and must pass the strict profile validator.

## Strict Validation

Use strict validation before claiming a generator profile is field-calibrated:

```bash
estate-triage validate-generator-profile \
  --profile-config profile.yml \
  --require-field-derived
```

Strict validation requires:

1. `source` must identify sanitized field-derived calibration.
2. `calibration_evidence` must be present.
3. `assessment_count` must be at least `1`.
4. `inventory_rows_observed` must be at least `1`.
5. Scenario counts must be non-negative and map to known generator scenarios.
6. The profile must generate at least one inventory row.

## Derive A Profile From A Sanitized Assessment

Once a bundle has been analyzed and redacted, derive a generator profile from the sanitized assessment artifact:

```bash
estate-triage analyze-bundle estate-bundle --top-n 25

estate-triage derive-generator-profile \
  --bundle estate-bundle \
  --output profiles/field-derived-profile.yml \
  --name field-derived-profile \
  --source sanitized-field-derived \
  --sanitization-method "strict redacted assessment artifact" \
  --source-window 2026-Q1

estate-triage validate-generator-profile \
  --profile-config profiles/field-derived-profile.yml \
  --require-field-derived
```

The derivation command uses existing deterministic assessment traces to map workloads into generator scenario buckets. It does not infer business truth; it creates a reproducible profile that can be reviewed, versioned, and used for future synthetic coverage generation.

Profile validation reports:

1. Scenario counts.
2. Scenario frequencies.
3. 95 percent Wilson confidence intervals for scenario frequencies.
4. A deterministic one-hot scenario correlation matrix.

The correlation matrix is useful for detecting whether the current generator profile is only modeling mutually exclusive buckets. Richer field-derived profiles may later add multi-label indicators for stronger correlation modeling.

## Field-Derived Profile Shape

```yaml
name: sanitized-field-profile
source: sanitized-field-derived
description: Scenario mix derived from sanitized local assessment evidence.
calibration_evidence:
  assessment_count: 3
  inventory_rows_observed: 1200
  backup_rows_observed: 1100
  utilization_rows_observed: 400
  sanitization_method: local redaction and aggregated scenario counts
  source_window: 2026-Q1
  notes:
    - Raw customer identifiers were not retained.
scenario_counts:
  migration_easy: 240
  dr_large_low_change: 80
  archive_powered_off_stale: 120
  rightsizing_util_backed: 90
  allocation_only_rightsizing: 70
  snapshot_blocker: 45
  no_backup_match: 60
  name_only_match: 35
  missing_storage_used: 25
  uuid_name_conflict: 15
  duplicate_name_candidates: 15
  ambiguous_backup_date: 10
backup_only_unmatched_rows: 35
notes:
  - Counts are aggregated and sanitized.
```

## Closure Boundary

The repository now has:

1. A generator profile schema.
2. Built-in synthetic profiles.
3. Custom profile loading.
4. Strict field-derived validation.
5. Calibration evidence metadata.
6. A derivation command for sanitized bundle assessments.
7. Tests proving synthetic profiles fail strict field-derived validation.

What the repository still does not contain is actual sanitized field-derived profile data. That data must come from real reviewed assessments. Without it, the generator remains coverage-complete and calibration-ready, but not field-calibrated.
