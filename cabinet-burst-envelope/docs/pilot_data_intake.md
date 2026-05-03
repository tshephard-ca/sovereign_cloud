# Pilot Data Intake

Use this checklist for a real-world pilot while preserving the local-only and review-only boundary.

Required files:

- `pdu_power.csv`
- `inlet_temps.csv`
- `cabinet_profile.yml`

Optional files:

- `thresholds.yml`
- `case_manifest.yml` for business context and expected review lane
- `notes.md`
- `annotations.csv` for offline maintenance, cooling-state, containment, or neighboring-cabinet notes
- anonymized facility outcome CSV for calibration

Minimum intake expectations:

- Seven days of cabinet power telemetry.
- Seven days of inlet-temperature telemetry.
- Top, middle, and bottom front inlet sensors when available.
- User-supplied sustained electrical limit.
- User-supplied burst limit and duration, if burst is allowed.
- User-supplied trip-risk threshold.
- User-supplied inlet warning and critical thresholds.

Run local pilot intake:

```bash
cabinet-burst-envelope pilot-intake \
  --input-root pilot_cases \
  --outcomes-csv pilot_outcomes.csv \
  --output-json out/pilot_report.json \
  --output-markdown out/pilot_report.md
```

Outcome CSV columns:

```csv
cabinet_id,facility_review_outcome,facility_sustained_kw,facility_burst_kw,review_minutes,remediation_required
```

Allowed outcome values should be local pilot labels such as:

- `approved_with_changes`
- `deferred`
- `rejected`
- `unknown`

Use the pilot report to calibrate review-lane ratios, action-owner queues, synthetic scenario ratios, observed p95 power ranges, inlet-temperature ranges, telemetry coverage assumptions, and review workflow metrics. Do not treat pilot outcome comparison as automatic approval.

For portfolio business-impact metrics without facility outcomes:

```bash
cabinet-burst-envelope business-impact \
  --input-root pilot_cases \
  --output-json out/business_impact.json \
  --output-markdown out/business_impact.md
```

Before external sharing:

```bash
cabinet-burst-envelope evidence-bundle --redact ...
```

or:

```bash
cabinet-burst-envelope redact-bundle --input case_or_bundle --output redacted_case_or_bundle
```
