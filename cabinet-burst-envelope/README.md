# cabinet-burst-envelope

## What The Project Does

`cabinet-burst-envelope` is a local-only cabinet review-lane engine for high-density or bursty workload conversations. It turns normalized PDU power readings, inlet-temperature telemetry, and user-supplied site limits into a conservative review packet for one cabinet.

The core business question is:

> Which review lane is this cabinet in, why, and what evidence or remediation is needed before the next conversation?

The tool produces a review-only envelope, a decision-lane JSON file, an action queue, an evidence packet, and a human-readable cabinet review packet. It is intended for sales engineering, operations, and facility engineering preflight before discussing additional bursty or high-density workload placement.

## What The Project Does Not Do

This project does not perform DCIM, CFD, cooling optimization, power reservation, customer quoting, BMS control, PDU control, live monitoring, alerting, capacity planning, rack layout optimization, power-path engineering, price calculation, contract generation, or automatic sales approval.

It does not change PDU settings, cooling settings, BMS settings, DCIM records, customer contracts, breaker limits, power reservations, or cabinet allocations.

## Why This Exists

AI, GPU, and other high-density workloads are often discussed before the cabinet-level power, thermal, feed, and evidence-quality story is clear. Operators may already have PDU and inlet-temperature telemetry, but the business workflow still needs a repeatable way to decide whether a cabinet can enter facility review, needs remediation, should stop expansion discussion, or simply lacks enough evidence.

The value is not "generate a report." The value is reducing unsafe or wasteful capacity conversations before they consume facility engineering, sales engineering, operations, and customer-facing time.

## Quickstart

```bash
cabinet-burst-envelope assess \
  --case-dir examples/cabinet_a01 \
  --output-dir out/cabinet_a01
```

For deterministic examples, add:

```bash
--now 2026-01-01T00:00:00Z
```

The assessment packet contains:

- `decision.json`: the review lane, business action, decision owner, evidence gate, and decision trace.
- `action_queue.json`: deterministic next actions grouped by owner and reason code.
- `cabinet_review_packet.md`: a one-page decision card followed by evidence and caveats.
- `envelope.json`: the review-only sustained and burst envelope.
- `summary.json`: the compact business and technical summary.
- `aligned_timeseries.csv`: aligned power and inlet-temperature evidence.
- `facility_review_worksheet.md`: handoff questions for human review.
- `manifest.json` and `input_fingerprints.json`: local evidence packet metadata.

## Review Lanes

- `READY_FOR_FACILITY_REVIEW`: evidence is strong enough to start a human facility review conversation within the review-only guardrail.
- `NEEDS_REMEDIATION`: a risk signal exists, such as thermal or electrical risk, and should be resolved before the cabinet is treated as ready.
- `STOP_EXPANSION_DISCUSSION`: a hard blocker or stop condition is present. Do not discuss additional bursty load for this cabinet until remediation is complete and the case is rerun.
- `COLLECT_EVIDENCE`: required telemetry, profile limits, sensor coverage, or evidence quality is missing or weak.

These lanes are not approvals, reservations, quotes, or operational instructions. They are preflight workflow lanes.

## Case Directory Contract

A case directory should contain:

- `pdu_power.csv`
- `inlet_temps.csv`
- `cabinet_profile.yml`
- optional `thresholds.yml`
- optional `case_manifest.yml`

`case_manifest.yml` gives business context without changing the calculation. It can state the case goal, expected review lane, review owner, remediation owner, and claims the packet must not make. The core calculation still comes from telemetry plus the cabinet profile.

## Business Workflows

The core CLI now supports the review workflow around the single-cabinet estimator:

```bash
cabinet-burst-envelope doctor \
  --power examples/cabinet_a01/pdu_power.csv \
  --temperature examples/cabinet_a01/inlet_temps.csv \
  --cabinet-profile examples/cabinet_a01/cabinet_profile.yml \
  --config examples/thresholds.yml \
  --now 2026-01-01T00:00:00Z \
  --format json
```

```bash
cabinet-burst-envelope evidence-bundle \
  --power examples/cabinet_a01/pdu_power.csv \
  --temperature examples/cabinet_a01/inlet_temps.csv \
  --cabinet-profile examples/cabinet_a01/cabinet_profile.yml \
  --config examples/thresholds.yml \
  --output-dir out/evidence \
  --now 2026-01-01T00:00:00Z
```

```bash
cabinet-burst-envelope batch \
  --input-root examples \
  --output-csv out/portfolio.csv \
  --output-json out/portfolio.json \
  --now 2026-01-01T00:00:00Z
```

```bash
cabinet-burst-envelope drift \
  --previous-envelope out/previous/envelope.json \
  --current-envelope out/current/envelope.json \
  --output-json out/drift.json \
  --output-markdown out/drift.md
```

```bash
cabinet-burst-envelope worksheet \
  --envelope out/envelope.json \
  --output-markdown out/facility_review_worksheet.md
```

Machine-readable explanation output:

```bash
cabinet-burst-envelope explain \
  --envelope out/envelope.json \
  --output-json out/envelope_explanation.json
```

```bash
cabinet-burst-envelope redact-bundle \
  --input out/evidence \
  --output out/evidence_redacted
```

These commands keep the project narrow: they create review packages, diagnostics, drift comparisons, pilot calibration reports, business-impact summaries, and human-review worksheets. They do not approve capacity or execute operational changes.

`doctor` includes a preflight checklist for power data, temperature data, aligned coverage, profile validity, electrical limits, trip threshold, thermal limits, inlet sensors, all-zero power, and blockers.

`batch` groups cabinets into remediation categories:

- `sensor_remediation`
- `profile_limits_required`
- `power_limited`
- `thermal_limited`
- `telemetry_quality`
- `feed_review`

## Generating Required Data

The project includes a deterministic synthetic data generator for product demos, regression tests, partner handoff examples, and scenario validation. It generates normalized CSV and YAML only.

List available scenarios:

```bash
cabinet-burst-envelope synthesize --list --output-dir out/unused
```

Generate one complete scenario:

```bash
cabinet-burst-envelope synthesize \
  --scenario healthy_margin \
  --output-dir out/synthetic/healthy_margin \
  --seed 7
```

Generate the full scenario corpus:

```bash
cabinet-burst-envelope synthesize \
  --all \
  --output-dir out/synthetic_corpus \
  --seed 7
```

Run the synthetic benchmark, which generates all built-in scenarios, estimates each one, and checks expected status, confidence, limiting factor, blocker, warning, missing-data, reason-code, and guardrail-range contracts:

```bash
cabinet-burst-envelope benchmark \
  --output-dir out/benchmark \
  --seed 7
```

The benchmark also checks schema shape, required input headers, input diversity, output status diversity, thermal/electrical/data-quality coverage, forbidden commitment language, absence of numeric recommendations for insufficient-data cases, and whether universal review-only caveats are kept out of warning lists. Release review should still run an external provider-name scan so the repo remains generic.

Each generated scenario contains:

- `pdu_power.csv`
- `inlet_temps.csv`
- `cabinet_profile.yml`
- `thresholds.yml`
- `scenario_manifest.yml`
- `expected_envelope.json`
- optional `annotations.csv` for offline maintenance, cooling-state, or neighboring-cabinet events

The generator covers healthy margin, electrical limits, thermal limits, burst near trip threshold, current load above guardrail, all-zero power, top inlet hotspot, thermal creep, cooling-state changes, neighboring-cabinet heat events, sensor drift, missing inlet sensors, ambient-only sensing, low power variation, low temperature variation, negative thermal slope, low coverage, long gaps, ten-minute cadence, stale readings, estimated readings, timestamp jitter, out-of-order rows, duplicate readings, rich optional electrical and humidity/dewpoint fields, unknown reading scope, total cabinet readings, feed total readings, outlet readings, feed imbalance, redundant feed survival risk, weekday/weekend cycles, burst-heavy workload, maintenance windows, high-density air-cooled profile, liquid-cooled profile, hybrid profile, naive timestamps, multiple cabinet IDs, missing electrical limits, missing thermal limits, burst limit below sustained limit, trip threshold below configured limit, and thermal critical threshold below warning threshold.

Important generator controls:

- `--days`
- `--bucket-minutes`
- `--seed`
- `--cabinet-id`
- `--base-kw`
- `--burst-kw`
- `--burst-frequency`
- `--thermal-slope`
- `--thermal-lag-minutes`
- `--noise`
- `--missing-power-pct`
- `--missing-temp-pct`
- `--sensor-set top,middle,bottom`
- `--feed-imbalance-pct`
- `--reading-scope total_cabinet|feed_total|outlet|unknown`

For real-world pilots, collect only the normalized input files and the user-supplied cabinet profile. Before sharing outputs, create a redacted handoff bundle:

```bash
cabinet-burst-envelope redact-bundle \
  --input site_case_or_evidence_bundle \
  --output redacted_case_or_bundle
```

The redacted bundle preserves kW values, temperatures, thresholds, status, confidence, risks, reason codes, warnings, blockers, and timestamps while replacing cabinet, PDU, sensor, circuit, and source identifiers.

Generate a local-only pilot calibration report from anonymized normalized cabinet cases:

```bash
cabinet-burst-envelope pilot-intake \
  --input-root pilot_cases \
  --outcomes-csv pilot_outcomes.csv \
  --output-json out/pilot_report.json \
  --output-markdown out/pilot_report.md \
  --now 2026-01-01T00:00:00Z
```

The optional outcome CSV is intentionally narrow:

```csv
cabinet_id,facility_review_outcome,facility_sustained_kw,facility_burst_kw,review_minutes,remediation_required
cab-001,approved_with_changes,21.6,25.6,45,false
```

Generate a business-impact summary without facility outcomes:

```bash
cabinet-burst-envelope business-impact \
  --input-root pilot_cases \
  --output-json out/business_impact.json \
  --output-markdown out/business_impact.md \
  --now 2026-01-01T00:00:00Z
```

These reports estimate review workflow impact only: ready-for-review counts, remediation queue counts, limiting-factor mix, telemetry-quality issues, and generator calibration hints. They are not capacity approval, pricing, quoting, or customer commitments.

## Output Contracts

JSON outputs carry explicit schema and tool versions. Schemas are stored in `schemas/`:

- `schemas/envelope.schema.json`
- `schemas/summary.schema.json`
- `schemas/review_lane.schema.json`
- `schemas/action_queue.schema.json`
- `schemas/case_manifest.schema.json`
- `schemas/assessment_packet.schema.json`
- `schemas/manifest.schema.json`
- `schemas/scenario_manifest.schema.json`
- `schemas/cabinet_profile.schema.json`
- `schemas/explanation.schema.json`

Decision JSON is the primary business output. It contains the review lane, business action, decision owner, primary constraint, evidence gate, action queue, boundary language, and traceable reason codes.

Envelope JSON includes an `evidence_quality` block with a 0-100 score, a quality band, coverage metrics, sensor completeness, warning count, blocker count, and missing-data count.

Thermal output also reports the best observed power-to-temperature lag tested by the simple model. This is evidence for review only; it is not CFD, cooling-capacity proof, or a live control signal.

## Policy Packs

Built-in policy packs adjust thresholds and language only. They do not replace site engineering or user-supplied cabinet limits.

```bash
cabinet-burst-envelope policy-packs
```

Use a built-in policy pack:

```bash
cabinet-burst-envelope estimate \
  --power examples/cabinet_a01/pdu_power.csv \
  --temperature examples/cabinet_a01/inlet_temps.csv \
  --cabinet-profile examples/cabinet_a01/cabinet_profile.yml \
  --policy-pack conservative-air-cooled \
  --output-envelope out/envelope.json
```

Available built-in packs:

- `conservative-air-cooled`
- `sales-prequalification`
- `operations-review`

You may also pass a local YAML policy pack path. Explicit `--config` threshold overrides are merged after the policy pack.

## Release And Adapter Documentation

Additional operational docs are included:

- `docs/pilot_data_intake.md`
- `docs/adapter_authoring.md`
- `docs/architecture.md`
- `docs/release_process.md`

Generate local release fingerprints and an SPDX-style file inventory:

```bash
cabinet-burst-envelope release-report \
  --repo-root . \
  --output-dir out/release
```

## Input: PDU Power CSV

The power input is normalized CSV, not a raw device export. Required columns are `timestamp`, `cabinet_id`, and `reading_kw`.

Strongly preferred columns are `feed_id`, `pdu_id`, `reading_scope`, and `source`. Optional columns include phase, circuit, voltage, current, apparent power, power factor, outlet, reading quality, and source row ID.

The MVP uses `reading_kw` only. It does not infer kW from amps and volts because the core must not assume site electrical topology. Raw PDU, DCIM, BMS, SNMP, Modbus, BACnet, Redfish, SSH, and telemetry-export formats are out of scope for core parsing.

## Input: Inlet-Temperature CSV

The temperature input is normalized CSV. Required columns are `timestamp`, `cabinet_id`, `sensor_id`, and `inlet_temp_c`.

Use `position`, `height`, and `sensor_role` to describe whether a sensor is top, middle, bottom, front, rear, inlet, outlet, ambient, or unknown. Envelope decisions use max inlet temperature per bucket. The tool does not average away hot spots.

## Input: Cabinet Profile YAML

The cabinet profile is the site-supplied contract. It provides limits that telemetry cannot know:

- sustained electrical limit
- burst electrical limit
- trip-risk threshold
- inlet warning and critical temperatures
- guardbands
- redundancy policy
- sales and operations review policy

The tool must never invent site limits. If electrical limits are missing, trip-risk threshold is unknown. If thermal limits are missing, thermal-risk threshold is unknown. If both are missing, the result is insufficient.

## Output Interpretation

- `READY_FOR_REVIEW` means a review-only envelope was calculated with adequate evidence.
- `REVIEW_REQUIRED` means evidence is incomplete or risk requires human review.
- `DO_NOT_EXPAND` means current evidence suggests the cabinet should not take additional load without remediation or engineering approval.
- `INSUFFICIENT_DATA` means the tool could not calculate a credible envelope. Recommended sustained and burst kW values are unavailable in this status.

None of these mean the cabinet is approved for sale, production, deployment, or any operational change.

For business workflows, prefer the review lane in `decision.json`. The envelope status explains the technical calculation state; the review lane explains what conversation should happen next.

## Reason-Code Dictionary

Input and data codes:

- `POWER_DATA_PRESENT`
- `POWER_DATA_MISSING`
- `TEMPERATURE_DATA_PRESENT`
- `TEMPERATURE_DATA_MISSING`
- `CABINET_PROFILE_PRESENT`
- `CABINET_PROFILE_MISSING`
- `MULTIPLE_CABINETS_IN_INPUT`
- `TIMESTAMP_TIMEZONE_UNKNOWN`
- `POWER_COVERAGE_LOW`
- `TEMPERATURE_COVERAGE_LOW`
- `ALIGNED_COVERAGE_LOW`
- `LONG_POWER_GAP`
- `LONG_TEMPERATURE_GAP`
- `READING_SCOPE_UNKNOWN`
- `ESTIMATED_POWER_READINGS_PRESENT`
- `STALE_POWER_READINGS_PRESENT`
- `ESTIMATED_TEMPERATURE_READINGS_PRESENT`
- `STALE_TEMPERATURE_READINGS_PRESENT`
- `ALL_ZERO_POWER_READINGS`
- `PROFILE_INVALID`

Sensor codes:

- `TOP_MIDDLE_BOTTOM_SENSORS_PRESENT`
- `MISSING_TOP_INLET_SENSOR`
- `MISSING_MIDDLE_INLET_SENSOR`
- `MISSING_BOTTOM_INLET_SENSOR`
- `NO_VALID_INLET_SENSOR`
- `AMBIENT_SENSOR_ONLY`
- `HOTSPOT_TOP_INLET`
- `INLET_TEMP_WARNING_OBSERVED`
- `INLET_TEMP_CRITICAL_OBSERVED`

Electrical codes:

- `ELECTRICAL_LIMIT_PRESENT`
- `ELECTRICAL_LIMIT_MISSING`
- `BURST_LIMIT_PRESENT`
- `BURST_LIMIT_NOT_SUPPLIED`
- `TRIP_THRESHOLD_PRESENT`
- `TRIP_THRESHOLD_NOT_SUPPLIED`
- `ELECTRICAL_GUARDBAND_APPLIED`
- `CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL`
- `CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL`
- `MEDIUM_TRIP_RISK`
- `HIGH_TRIP_RISK`
- `FEED_IMBALANCE_WARNING`
- `FEED_IMBALANCE_CRITICAL`
- `REDUNDANCY_MODE_UNKNOWN`
- `SINGLE_FEED_SURVIVAL_NOT_EVALUATED`
- `SINGLE_FEED_SURVIVAL_RISK`
- `BURST_LIMIT_BELOW_SUSTAINED_LIMIT`
- `TRIP_THRESHOLD_BELOW_SUSTAINED_LIMIT`
- `TRIP_THRESHOLD_BELOW_BURST_LIMIT`
- `NEGATIVE_FEED_LIMIT`
- `NEGATIVE_FEED_TRIP_THRESHOLD`
- `FEED_TRIP_THRESHOLD_BELOW_FEED_LIMIT`

Thermal codes:

- `THERMAL_LIMIT_PRESENT`
- `THERMAL_LIMIT_MISSING`
- `THERMAL_MODEL_USABLE`
- `THERMAL_MODEL_UNUSABLE`
- `THERMAL_MODEL_LOW_R2`
- `POWER_VARIATION_TOO_LOW_FOR_THERMAL_MODEL`
- `TEMP_VARIATION_TOO_LOW_FOR_THERMAL_MODEL`
- `THERMAL_SLOPE_NOT_POSITIVE`
- `THERMAL_EXTRAPOLATION_CAPPED`
- `THERMAL_GUARDBAND_APPLIED`
- `CURRENT_LOAD_NEAR_OR_ABOVE_THERMAL_LIMIT`
- `MEDIUM_THERMAL_RISK`
- `HIGH_THERMAL_RISK`
- `THERMAL_RISK_UNKNOWN`
- `THERMAL_CRITICAL_BELOW_WARNING_LIMIT`
- `NEGATIVE_THERMAL_EXTRAPOLATION_LIMIT`

Envelope codes:

- `ENVELOPE_READY_FOR_REVIEW`
- `ENVELOPE_REVIEW_REQUIRED`
- `ENVELOPE_DO_NOT_EXPAND`
- `ENVELOPE_INSUFFICIENT_DATA`
- `LIMITING_FACTOR_ELECTRICAL`
- `LIMITING_FACTOR_THERMAL`
- `LIMITING_FACTOR_BOTH`
- `LIMITING_FACTOR_DATA_QUALITY`
- `REVIEW_ONLY_OUTPUT`
- `ALL_ZERO_POWER_READINGS`
- `HUMAN_REVIEW_REQUIRED`
- `LOW_CONFIDENCE_DISCUSSION_GUARDRAIL`

Blockers:

- `POWER_DATA_MISSING`
- `TEMPERATURE_DATA_MISSING`
- `CABINET_PROFILE_MISSING`
- `NO_VALID_INLET_SENSOR`
- `ELECTRICAL_LIMIT_MISSING`
- `MULTIPLE_CABINETS_IN_INPUT`
- `ALIGNED_COVERAGE_TOO_LOW`
- `CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL`
- `CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL`
- `INLET_TEMP_CRITICAL_OBSERVED`
- `HIGH_TRIP_RISK`
- `FEED_IMBALANCE_CRITICAL`
- `SINGLE_FEED_SURVIVAL_RISK`
- `PROFILE_INVALID`
- `ALL_ZERO_POWER_READINGS`

Warnings:

- `TIMESTAMP_TIMEZONE_UNKNOWN`
- `POWER_COVERAGE_LOW`
- `TEMPERATURE_COVERAGE_LOW`
- `ALIGNED_COVERAGE_LOW`
- `LONG_POWER_GAP`
- `LONG_TEMPERATURE_GAP`
- `MISSING_TOP_INLET_SENSOR`
- `MISSING_MIDDLE_INLET_SENSOR`
- `MISSING_BOTTOM_INLET_SENSOR`
- `BURST_LIMIT_NOT_SUPPLIED`
- `TRIP_THRESHOLD_NOT_SUPPLIED`
- `THERMAL_MODEL_UNUSABLE`
- `THERMAL_MODEL_LOW_R2`
- `POWER_VARIATION_TOO_LOW_FOR_THERMAL_MODEL`
- `TEMP_VARIATION_TOO_LOW_FOR_THERMAL_MODEL`
- `FEED_IMBALANCE_WARNING`
- `INLET_TEMP_WARNING_OBSERVED`
- `MEDIUM_TRIP_RISK`
- `MEDIUM_THERMAL_RISK`

Missing-data values:

- `POWER_DATA_MISSING`
- `TEMPERATURE_DATA_MISSING`
- `CABINET_PROFILE_MISSING`
- `PROFILE_INVALID`
- `NO_VALID_INLET_SENSOR`
- `MISSING_TOP_INLET_SENSOR`
- `MISSING_MIDDLE_INLET_SENSOR`
- `MISSING_BOTTOM_INLET_SENSOR`

## Data Honesty Caveats

1. Seven days of telemetry may not include worst-case weather, cooling failures, maintenance modes, or customer workload peaks.
2. PDU power telemetry is not a full electrical study.
3. Inlet-temperature telemetry is not CFD.
4. A simple thermal slope is not proof of cooling capacity.
5. Low inlet temperature at current load does not guarantee headroom at higher load.
6. Thermal behavior may change with blanking panels, cable management, fan curves, liquid-cooling state, containment, or neighboring cabinets.
7. Trip thresholds must come from site policy or engineering data, not from this tool.
8. Sales guardrails are review aids, not binding commitments.
9. Facility engineering approval is required before using results operationally.

## Privacy And Security

- local-only
- offline-only
- no telemetry
- no external calls
- no credentials
- no PDU login
- no BMS login
- no DCIM API calls
- no SNMP
- no Modbus
- no BACnet
- no Redfish
- no SSH
- no live controls

Outputs may contain cabinet IDs, PDU IDs, sensor IDs, circuit IDs, and operational thresholds. Use `--redact` before sharing outputs.

## Proprietary And Platform Boundary

- The repo consumes normalized CSV and YAML only.
- The repo does not bundle or invoke DCIM, PDU, BMS, SNMP, Modbus, BACnet, Redfish, or facility-management tools.
- Users supply telemetry they are authorized to analyze.
- Future site-specific collectors should be optional adapters.
- Core logic should remain vendor-neutral, offline-first, and review-only.

## Implemented Core Workflows

- Golden-path `assess` command that writes a complete cabinet review packet.
- Decision-lane classification with action queue, evidence gate, business action, and decision trace.
- Single-cabinet estimate with JSON, CSV, Markdown, and summary outputs.
- Input doctor with missing-data questions, preflight checklist, and evidence-quality scoring.
- Deterministic synthetic scenario generation for demos and regression cases.
- Synthetic benchmark generation and expected-contract checks.
- Benchmark schema, language-safety, input-diversity, and output-realism gates.
- Pilot data intake with optional anonymized facility outcome comparison.
- Business-impact report for review queue and remediation triage metrics.
- Evidence bundle generation with manifest and input fingerprints.
- Redacted handoff bundle generation.
- Batch portfolio CSV/JSON over many cabinet case directories with remediation grouping.
- Drift comparison between two envelope JSON files.
- Facility engineering review worksheet.
- JSON Schema files for core output and manifest contracts.
- Policy packs for threshold posture only.
- Release report generation with fingerprints and SPDX-style file inventory.

## Remaining Expansion Roadmap

1. Liquid-cooling telemetry extension

   Accept optional liquid-cooling telemetry CSV for supply coolant temperature, return coolant temperature, flow rate, and coolant-unit alarm state. Keep this as an extension, not MVP.

2. Review-lane portfolio drilldown

   Expand portfolio output with trend views over review lanes, action owners, and remediation aging. Do not include pricing, quoting, customer contract generation, or capacity approval.

3. Optional telemetry adapters

    Future separate packages may transform PDU/DCIM/BMS exports into normalized CSV. Core must not include proprietary connectors.

4. Executor interface: explicitly out of scope

    Do not add live control executors. If future projects add them, they must be separate packages with explicit approvals, credentials handling, audit logs, rollback, and site-specific safety review.
