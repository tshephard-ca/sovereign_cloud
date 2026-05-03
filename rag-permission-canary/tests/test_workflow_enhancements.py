import csv
import json
import zipfile

from typer.testing import CliRunner

from rag_permission_canary.access_matrix import ACCESS_MATRIX_COLUMNS, BOUNDARY_COVERAGE_COLUMNS
from rag_permission_canary.cli import app


runner = CliRunner()


def test_generate_demo_fixtures_creates_strong_input_pack(tmp_path):
    out = tmp_path / "demo"
    result = runner.invoke(app, ["generate-demo-fixtures", "--output-dir", str(out), "--users", "4", "--documents", "20", "--seed", "7", "--now", "2026-01-01T00:00:00Z"])
    assert result.exit_code == 0, result.output
    quality = json.loads((out / "fixture_quality.json").read_text(encoding="utf-8"))
    assert quality["quality_grade"] == "STRONG"
    assert quality["summary"]["allowed_user_doc_pairs"] >= 10
    assert quality["summary"]["forbidden_user_doc_pairs"] >= 10
    assert quality["warnings"] == []
    with (out / "access_matrix.csv").open(encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == ACCESS_MATRIX_COLUMNS
    with (out / "boundary_coverage.csv").open(encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == BOUNDARY_COVERAGE_COLUMNS


def test_run_demo_safe_and_leaky_make_release_decision(tmp_path):
    safe = tmp_path / "safe"
    leaky = tmp_path / "leaky"
    safe_result = runner.invoke(app, ["run-demo", "--output-dir", str(safe), "--mode", "safe", "--seed", "7", "--force", "--now", "2026-01-01T00:00:00Z"])
    leaky_result = runner.invoke(app, ["run-demo", "--output-dir", str(leaky), "--mode", "leaky", "--seed", "7", "--force", "--now", "2026-01-01T00:00:00Z"])
    assert safe_result.exit_code == 0, safe_result.output
    assert leaky_result.exit_code == 0, leaky_result.output
    safe_results = json.loads((safe / "run_safe" / "results.json").read_text(encoding="utf-8"))
    leaky_results = json.loads((leaky / "run_leaky" / "results.json").read_text(encoding="utf-8"))
    assert safe_results["aggregate_status"] == "PASS"
    assert safe_results["decision"]["release_decision"] == "ALLOW_NEXT_STAGE"
    assert safe_results["decision"]["confidence"] == "HIGH"
    assert leaky_results["aggregate_status"] == "FAIL"
    assert leaky_results["decision"]["release_decision"] == "BLOCK_RELEASE"
    assert leaky_results["decision"]["recommended_owner"] == "retrieval_endpoint_owner"
    assert leaky_results["leakage_summary"]["forbidden_raw_context_leaks"] > 0


def test_assess_fixture_outputs_quality_and_boundary_artifacts(tmp_path):
    demo = tmp_path / "demo"
    runner.invoke(app, ["generate-demo-fixtures", "--output-dir", str(demo), "--seed", "8"])
    result = runner.invoke(
        app,
        [
            "assess-fixture",
            "--content",
            str(demo / "content_set.yml"),
            "--users",
            str(demo / "test_users.yml"),
            "--permissions",
            str(demo / "permissions.yml"),
            "--endpoint",
            str(demo / "endpoint.yml"),
            "--config",
            str(demo / "thresholds.yml"),
            "--pack",
            str(demo / "canary_pack.yml"),
            "--output-quality-json",
            str(tmp_path / "quality.json"),
            "--output-quality-markdown",
            str(tmp_path / "quality.md"),
            "--output-access-matrix",
            str(tmp_path / "access.csv"),
            "--output-boundary-coverage",
            str(tmp_path / "boundary.csv"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "fixture quality: STRONG" in result.output
    assert (tmp_path / "quality.md").exists()
    assert (tmp_path / "access.csv").exists()
    assert (tmp_path / "boundary.csv").exists()


def test_handoff_bundle_contains_review_artifacts(tmp_path):
    out = tmp_path / "demo"
    runner.invoke(app, ["run-demo", "--output-dir", str(out), "--mode", "safe", "--force"])
    bundle = tmp_path / "handoff.zip"
    result = runner.invoke(
        app,
        [
            "handoff-bundle",
            "--output-zip",
            str(bundle),
            "--pack",
            str(out / "canary_pack.yml"),
            "--queries",
            str(out / "canary_queries.csv"),
            "--results",
            str(out / "run_safe" / "results.json"),
            "--test-results",
            str(out / "run_safe" / "test_results.csv"),
            "--report",
            str(out / "run_safe" / "permission_regression_report.md"),
            "--junit",
            str(out / "run_safe" / "junit.xml"),
            "--fixture-quality",
            str(out / "run_safe" / "fixture_quality.json"),
            "--access-matrix",
            str(out / "run_safe" / "access_matrix.csv"),
            "--boundary-coverage",
            str(out / "run_safe" / "boundary_coverage.csv"),
            "--endpoint",
            str(out / "endpoint.yml"),
            "--config",
            str(out / "thresholds.yml"),
        ],
    )
    assert result.exit_code == 0, result.output
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "results/permission_regression_report.md" in names
    assert "coverage/access_matrix.csv" in names
    assert "quality/fixture_quality.json" in names


def test_report_starts_with_decision_summary(tmp_path):
    out = tmp_path / "demo"
    runner.invoke(app, ["run-demo", "--output-dir", str(out), "--mode", "safe", "--force"])
    text = (out / "run_safe" / "permission_regression_report.md").read_text(encoding="utf-8")
    assert text.startswith("# RAG Permission Regression Report")
    assert "## Release Decision" in text
    assert "Decision: **ALLOW_NEXT_STAGE**" in text


def test_run_can_score_allowed_evidence_from_self_contained_pack(tmp_path):
    out = tmp_path / "demo"
    runner.invoke(app, ["run-demo", "--output-dir", str(out), "--mode", "safe", "--force"])
    pack = (out / "canary_pack.yml").read_text(encoding="utf-8")
    assert "target_canary_texts" in pack
