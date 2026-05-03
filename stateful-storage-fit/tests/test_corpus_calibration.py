import json
from pathlib import Path

import yaml

from stateful_storage_fit.corpus import case_template, evaluate_corpus
from stateful_storage_fit.engine import analyze_paths

from tests.helpers import DF_DATA, FSTAB_DATA, IOSTAT_LOW, MOUNT_DATA, PROFILE, PS_DB


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_corpus_outcomes_compute_readiness_and_pass_failure_rate(tmp_path):
    df = _write(tmp_path / "df.txt", DF_DATA)
    mount = _write(tmp_path / "mount.txt", MOUNT_DATA)
    fstab = _write(tmp_path / "fstab.txt", FSTAB_DATA)
    iostat = _write(tmp_path / "iostat.txt", IOSTAT_LOW)
    ps = _write(tmp_path / "ps.txt", PS_DB)
    profile = _write(tmp_path / "profile.yml", PROFILE)
    case = {
        "id": "outcome-pass-failed",
        "data_origin": "real_workload",
        "profile_origin": "user_supplied",
        "df": str(df),
        "mount": str(mount),
        "fstab": str(fstab),
        "iostat": str(iostat),
        "ps": str(ps),
        "storage_profile": str(profile),
        "engine_decision": {"fit_status": "PASS"},
        "expected_fit_status": "PASS",
        "expert_reviews": [{"reviewer_id": "r1", "fit_status": "PASS"}],
        "outcomes": [{"status": "failed_storage_assumption"}],
    }
    (tmp_path / "case.yml").write_text(yaml.safe_dump(case), encoding="utf-8")
    report = evaluate_corpus(
        tmp_path,
        min_outcome_cases=1,
        min_outcome_coverage=0.5,
        max_pass_storage_failure_rate=0.1,
    )
    assert report["outcome_linked_case_count"] == 1
    assert report["outcome_metrics"]["by_predicted_status"]["PASS"]["storage_failure_rate"] == 1.0
    assert "PASS_STORAGE_FAILURE_RATE_TOO_HIGH" in report["readiness"]["blockers"]


def test_calibration_report_conservatively_lowers_confidence(tmp_path):
    calibration_report = evaluate_corpus(Path("examples/corpus"))
    bundle = analyze_paths(
        df=_write(tmp_path / "df.txt", DF_DATA),
        mount=_write(tmp_path / "mount.txt", MOUNT_DATA),
        fstab=_write(tmp_path / "fstab.txt", FSTAB_DATA),
        iostat=_write(tmp_path / "iostat.txt", IOSTAT_LOW),
        ps=_write(tmp_path / "ps.txt", PS_DB),
        storage_profile_path=_write(tmp_path / "profile.yml", PROFILE),
        calibration_report=calibration_report,
    )
    assert "CALIBRATION_RESEARCH_ONLY" in bundle.result.warnings
    assert bundle.result.confidence != "HIGH"
    assert bundle.result.analysis["calibration"]["readiness_level"] == "RESEARCH_ONLY"


def test_case_template_includes_review_and_outcome_fields():
    template = case_template("case-001")
    assert "review_template" in template
    assert "outcome_template" in template
    assert "business_impact_template" in template
    assert template["expert_reviews"] == []
    assert template["outcomes"] == []
    assert template["id"] == "case-001"
