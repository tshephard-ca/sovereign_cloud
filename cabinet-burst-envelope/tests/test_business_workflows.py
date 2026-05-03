from __future__ import annotations

import csv
import json

from typer.testing import CliRunner

from cabinet_burst_envelope.cli import app


def _scenario(tmp_path, name="healthy_margin"):
    out = tmp_path / name
    result = CliRunner().invoke(app, ["synthesize", "--scenario", name, "--output-dir", str(out), "--seed", "5"])
    assert result.exit_code == 0, result.output
    return out


def test_doctor_evidence_bundle_worksheet_and_redacted_bundle(tmp_path):
    case = _scenario(tmp_path)
    runner = CliRunner()

    doctor = runner.invoke(
        app,
        [
            "doctor",
            "--power",
            str(case / "pdu_power.csv"),
            "--temperature",
            str(case / "inlet_temps.csv"),
            "--cabinet-profile",
            str(case / "cabinet_profile.yml"),
            "--config",
            str(case / "thresholds.yml"),
            "--now",
            "2026-01-01T00:00:00Z",
            "--format",
            "json",
        ],
    )
    assert doctor.exit_code == 0, doctor.output
    doctor_payload = json.loads(doctor.output)
    assert doctor_payload["schema_version"] == "cabinet-burst-envelope.doctor.v1"
    assert doctor_payload["evidence_quality"]["score"] >= 85
    assert doctor_payload["preflight_passed"] is True
    assert any(item["name"] == "top_middle_bottom_sensors_present" for item in doctor_payload["preflight_checklist"])

    bundle = tmp_path / "bundle"
    evidence = runner.invoke(
        app,
        [
            "evidence-bundle",
            "--power",
            str(case / "pdu_power.csv"),
            "--temperature",
            str(case / "inlet_temps.csv"),
            "--cabinet-profile",
            str(case / "cabinet_profile.yml"),
            "--config",
            str(case / "thresholds.yml"),
            "--output-dir",
            str(bundle),
            "--now",
            "2026-01-01T00:00:00Z",
        ],
    )
    assert evidence.exit_code == 0, evidence.output
    assert (bundle / "manifest.json").exists()
    assert (bundle / "input_fingerprints.json").exists()
    assert (bundle / "envelope_explanation.json").exists()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "cabinet-burst-envelope.manifest.v1"

    worksheet = runner.invoke(app, ["worksheet", "--envelope", str(bundle / "envelope.json"), "--output-markdown", str(tmp_path / "worksheet.md")])
    assert worksheet.exit_code == 0, worksheet.output
    assert "Human Signoff" in (tmp_path / "worksheet.md").read_text(encoding="utf-8")

    redacted = tmp_path / "redacted"
    redact = runner.invoke(app, ["redact-bundle", "--input", str(bundle), "--output", str(redacted)])
    assert redact.exit_code == 0, redact.output
    redacted_envelope = json.loads((redacted / "envelope.json").read_text(encoding="utf-8"))
    assert redacted_envelope["cabinet_id"] == "cabinet_001"
    assert redacted_envelope["recommended_sustained_kw"] == json.loads((bundle / "envelope.json").read_text(encoding="utf-8"))["recommended_sustained_kw"]


def test_batch_and_drift_workflows(tmp_path):
    healthy = _scenario(tmp_path, "healthy_margin")
    blocked = _scenario(tmp_path, "current_load_exceeds_guardrail")
    runner = CliRunner()

    portfolio_csv = tmp_path / "portfolio.csv"
    portfolio_json = tmp_path / "portfolio.json"
    batch = runner.invoke(
        app,
        [
            "batch",
            "--input-root",
            str(tmp_path),
            "--output-csv",
            str(portfolio_csv),
            "--output-json",
            str(portfolio_json),
            "--now",
            "2026-01-01T00:00:00Z",
        ],
    )
    assert batch.exit_code == 0, batch.output
    with portfolio_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    statuses = {row["cabinet_id"]: row["envelope_status"] for row in rows}
    assert statuses["cab-healthy-margin"] == "READY_FOR_REVIEW"
    assert statuses["cab-current-load-exceeds-guardrail"] == "DO_NOT_EXPAND"

    drift = runner.invoke(
        app,
        [
            "drift",
            "--previous-envelope",
            str(healthy / "expected_envelope.json"),
            "--current-envelope",
            str(blocked / "expected_envelope.json"),
            "--output-json",
            str(tmp_path / "drift.json"),
            "--output-markdown",
            str(tmp_path / "drift.md"),
            "--format",
            "json",
        ],
    )
    assert drift.exit_code == 0, drift.output
    drift_payload = json.loads(drift.output)
    assert drift_payload["schema_version"] == "cabinet-burst-envelope.drift.v1"
    assert drift_payload["status_current"] == "DO_NOT_EXPAND"
    assert "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL" in drift_payload["new_blockers"]


def test_release_report_generates_fingerprints_and_sbom(tmp_path):
    result = CliRunner().invoke(app, ["release-report", "--repo-root", ".", "--output-dir", str(tmp_path / "release")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "release" / "artifact_fingerprints.json").exists()
    assert (tmp_path / "release" / "sbom.spdx.json").exists()
    assert (tmp_path / "release" / "release_checklist.md").exists()
    payload = json.loads((tmp_path / "release" / "artifact_fingerprints.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "cabinet-burst-envelope.release.v1"
    assert payload["file_count"] > 0


def test_portfolio_groups_remediation_categories(tmp_path):
    _scenario(tmp_path, "missing_top_sensor")
    _scenario(tmp_path, "feed_imbalance_critical")
    result = CliRunner().invoke(
        app,
        [
            "batch",
            "--input-root",
            str(tmp_path),
            "--output-json",
            str(tmp_path / "portfolio.json"),
            "--now",
            "2026-01-01T00:00:00Z",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / "portfolio.json").read_text(encoding="utf-8"))
    assert "sensor_remediation" in payload["remediation_groups"]
    assert "feed_review" in payload["remediation_groups"]


def test_pilot_intake_generates_calibration_and_business_report(tmp_path):
    _scenario(tmp_path, "healthy_margin")
    _scenario(tmp_path, "thermal_limited")
    outcomes = tmp_path / "outcomes.csv"
    outcomes.write_text(
        "\n".join(
            [
                "cabinet_id,facility_review_outcome,facility_sustained_kw,facility_burst_kw,review_minutes,remediation_required",
                "cab-healthy-margin,approved_with_changes,21.6,25.6,45,false",
                "cab-thermal-limited,deferred,14.0,18.0,90,true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        [
            "pilot-intake",
            "--input-root",
            str(tmp_path),
            "--outcomes-csv",
            str(outcomes),
            "--output-json",
            str(tmp_path / "pilot.json"),
            "--output-markdown",
            str(tmp_path / "pilot.md"),
            "--now",
            "2026-01-01T00:00:00Z",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / "pilot.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "cabinet-burst-envelope.pilot_report.v1"
    assert payload["cabinet_count"] == 2
    assert payload["outcome_count"] == 2
    assert payload["outcome_alignment"]["available"] is True
    assert "business_impact" in payload
    assert "review_lane_counts" in payload
    assert "action_owner_counts" in payload
    assert "Generator Calibration Hints" in (tmp_path / "pilot.md").read_text(encoding="utf-8")


def test_business_impact_command_reports_review_queue_metrics(tmp_path):
    _scenario(tmp_path, "healthy_margin")
    _scenario(tmp_path, "missing_top_sensor")
    result = CliRunner().invoke(
        app,
        [
            "business-impact",
            "--input-root",
            str(tmp_path),
            "--output-json",
            str(tmp_path / "impact.json"),
            "--output-markdown",
            str(tmp_path / "impact.md"),
            "--now",
            "2026-01-01T00:00:00Z",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / "impact.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "cabinet-burst-envelope.business_impact.v1"
    assert payload["cabinet_count"] == 2
    assert "remediation_category_counts" in payload
    assert "review_lane_counts" in payload
    assert "Review-only workflow metrics" in (tmp_path / "impact.md").read_text(encoding="utf-8")
