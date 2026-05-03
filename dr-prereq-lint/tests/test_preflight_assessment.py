import csv
import json
import zipfile

from typer.testing import CliRunner

from dr_prereq_lint.assessment import build_preflight_assessment
from dr_prereq_lint.cli import app
from dr_prereq_lint.generate_data import generate_sample_data
from dr_prereq_lint.lint_rules import analyze_inputs
from dr_prereq_lint.support_files import load_owner_map


def test_preflight_assessment_groups_service_families_and_owner_work(tmp_path):
    generate_sample_data("missing-database-host", tmp_path)
    result = analyze_inputs(
        backup_inventory=tmp_path / "backup_inventory.csv",
        dns_log=tmp_path / "dns_queries.csv",
        recovery_set_name="dr-test-001",
        known_prereqs_path=tmp_path / "prerequisite_catalog.yml",
        resolver_hints_path=tmp_path / "required_resolvers.yml",
        config_path=tmp_path / "policy.yml",
    )
    assessment = build_preflight_assessment(findings=result.findings, summary=result.summary, owner_map=load_owner_map(tmp_path / "owner_map.csv"))
    families = {item.service_family: item for item in assessment.service_families}
    assert assessment.decision in {"FAIL", "REVIEW"}
    assert "data_services" in families
    assert any(item.owner_team == "database-team" for item in assessment.owner_work_items)
    assert assessment.evidence_improvement_actions
    assert "DNS query evidence shows lookups" in assessment.limitations[0]


def test_cli_analyze_accepts_business_aliases_and_writes_assessment(tmp_path):
    generate_sample_data("missing-database-host", tmp_path / "sample")
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--backup-inventory", str(tmp_path / "sample" / "backup_inventory.csv"),
            "--dns-log", str(tmp_path / "sample" / "dns_queries.csv"),
            "--recovery-set", "dr-test-001",
            "--prerequisite-catalog", str(tmp_path / "sample" / "prerequisite_catalog.yml"),
            "--required-resolvers", str(tmp_path / "sample" / "required_resolvers.yml"),
            "--policy", str(tmp_path / "sample" / "policy.yml"),
            "--owner-map", str(tmp_path / "sample" / "owner_map.csv"),
            "--output-coverage-gaps", str(out / "coverage_gaps.csv"),
            "--output-evidence-detail", str(out / "evidence_detail.csv"),
            "--summary", str(out / "summary.json"),
            "--output-assessment", str(out / "preflight_assessment.json"),
            "--output-owner-worklist", str(out / "owner_worklist.csv"),
        ],
    )
    assert result.exit_code == 0, result.output
    assessment = json.loads((out / "preflight_assessment.json").read_text(encoding="utf-8"))
    assert assessment["assessment_type"] == "recovery_preflight_assessment"
    assert assessment["owner_work_items"]
    with (out / "owner_worklist.csv").open("r", encoding="utf-8", newline="") as handle:
        assert "owner_team" in next(csv.reader(handle))


def test_cli_analyze_package_writes_complete_preflight_bundle(tmp_path):
    generate_sample_data("missing-database-host", tmp_path / "sample")
    out = tmp_path / "package-out"
    result = CliRunner().invoke(app, ["analyze-package", "--package", str(tmp_path / "sample" / "preflight_package.yml"), "--output-dir", str(out)])
    assert result.exit_code == 0, result.output
    expected = {
        "coverage_gaps.csv",
        "evidence_detail.csv",
        "summary.json",
        "preflight_assessment.json",
        "owner_worklist.csv",
        "preflight_report.md",
        "handoff_questions.md",
        "recovery_prereq_checklist.csv",
        "preflight_evidence_bundle.zip",
    }
    assert expected.issubset({path.name for path in out.iterdir()})
    assessment = json.loads((out / "preflight_assessment.json").read_text(encoding="utf-8"))
    assert assessment["business_impact"]
    assert any(item["service_family"] == "data_services" for item in assessment["service_families"])
    report = (out / "preflight_report.md").read_text(encoding="utf-8")
    assert "## Recovery-Scope Gaps By Service Family" in report
    assert "## Owner Routing" in report
    with zipfile.ZipFile(out / "preflight_evidence_bundle.zip") as archive:
        assert "preflight_assessment.json" in archive.namelist()
        assert "owner_worklist.csv" in archive.namelist()
