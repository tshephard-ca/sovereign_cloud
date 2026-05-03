import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from stateful_storage_fit.cli import app
from stateful_storage_fit.workflow import (
    add_impact,
    add_outcome,
    add_review,
    adjudicate_case,
    build_manifest,
    create_case_from_bundle,
    validate_bundle,
    validate_case,
)

from tests.helpers import DF_DATA, FSTAB_DATA, IOSTAT_LOW, MOUNT_DATA, PROFILE, PS_DB


runner = CliRunner()


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    _write(bundle / "df.txt", DF_DATA)
    _write(bundle / "mount.txt", MOUNT_DATA)
    _write(bundle / "fstab.txt", FSTAB_DATA)
    _write(bundle / "iostat.txt", IOSTAT_LOW)
    _write(bundle / "ps.txt", PS_DB)
    manifest = build_manifest(
        bundle,
        commands=[],
        collector_version="test",
        redaction_mode="none",
        safe_host_facts={"system": "test"},
    )
    _write(bundle / "manifest.json", json.dumps(manifest))
    return bundle


def test_bundle_validation_and_case_lifecycle(tmp_path):
    bundle = _bundle(tmp_path)
    profile = _write(tmp_path / "profile.yml", PROFILE)
    validation = validate_bundle(bundle)
    assert validation["valid"]
    assert validation["core_completeness_score"] == 1.0
    assert validation["overall_bundle_quality_score"] < 1.0

    case_path = tmp_path / "case.yml"
    create_case_from_bundle(case_id="case-001", bundle_dir=bundle, storage_profile_path=profile, output_path=case_path)
    created = validate_case(case_path)
    assert created["valid"]
    assert created["lifecycle_state"] == "engine_analyzed"

    review_a = _write(tmp_path / "review-a.yml", yaml.safe_dump({"reviewer_id": "a", "fit_status": "PASS"}))
    review_b = _write(tmp_path / "review-b.yml", yaml.safe_dump({"reviewer_id": "b", "fit_status": "PASS"}))
    add_review(case_path, review_a)
    reviewed = add_review(case_path, review_b)
    assert reviewed["lifecycle_state"] == "expert_reviewed"

    adjudicated = adjudicate_case(case_path)
    assert adjudicated["adjudicated_fit_status"] == "PASS"

    add_outcome(case_path, status="storage_fit_confirmed", notes="storage fit confirmed")
    add_impact(
        case_path,
        assessment_minutes=30,
        expert_review_minutes=15,
        blocker_found_before_pilot=False,
        failed_pilot_avoided=False,
        platform_gap_identified=False,
        decision="proceed",
    )
    final_validation = validate_case(case_path)
    assert final_validation["calibration_ready"]
    assert final_validation["outcome_quality_score"] >= 70
    assert final_validation["business_impact_quality_score"] >= 70
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert case["business_impact"][0]["assessment_minutes"] == 30


def test_cli_bundle_case_and_validation_commands(tmp_path):
    bundle = _bundle(tmp_path)
    profile = _write(tmp_path / "profile.yml", PROFILE)
    case_path = tmp_path / "case.yml"
    validation_out = tmp_path / "bundle-validation.json"
    result = runner.invoke(app, ["validate-bundle", "--bundle", str(bundle), "--output", str(validation_out)])
    assert result.exit_code == 0, result.output
    assert json.loads(validation_out.read_text(encoding="utf-8"))["valid"]

    result = runner.invoke(
        app,
        [
            "create-case",
            "--case-id",
            "case-cli",
            "--bundle",
            str(bundle),
            "--storage-profile",
            str(profile),
            "--output",
            str(case_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(case_path.read_text(encoding="utf-8"))["id"] == "case-cli"

    result = runner.invoke(app, ["validate-case", "--case", str(case_path)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["valid"]
