from __future__ import annotations

import json

from typer.testing import CliRunner

from s3_compat_replay.cli import app
from s3_compat_replay.matrix import build_matrix
from s3_compat_replay.models import Mismatch, OperationFamilyProfile, ProbeResult, ProbeResults, UsageProfile
from s3_compat_replay.policy import evaluate_policy, load_policy
from s3_compat_replay.questionnaire import generate_questionnaire
from s3_compat_replay.report import write_json


def _profile():
    return UsageProfile(
        source_bucket="bucket_001",
        event_count=10,
        processed_event_count=10,
        operation_families={
            "object_read": OperationFamilyProfile(count=5, event_names={"GetObject": 5}),
            "object_write": OperationFamilyProfile(count=5, event_names={"PutObject": 5}),
        },
        observed_features=["CORS", "PRESIGNED_OBSERVED", "OBJECT_TAGGING"],
        request_hint_features=["CORS", "PRESIGNED_OBSERVED"],
    )


def _results():
    mismatch = Mismatch(
        severity="BLOCKER",
        probe_id="cors_put_preflight",
        operation_family="cors",
        operation="OPTIONS",
        evidence_source="REQUEST_HINTS",
        expected="Access-Control-Allow-Origin present",
        actual="header absent",
        mismatch_code="CORS_PREFLIGHT_MISMATCH",
        reason_text="Target did not return expected CORS allow headers.",
        business_impact="Browser upload flows may fail.",
        suggested_human_question="Which browser origins, methods, and headers must be supported?",
    )
    return ProbeResults(
        run_id="run",
        endpoint_url_redacted="https://endpoint_redacted",
        target_bucket_redacted="bucket_002",
        scratch_prefix="compat-replay/",
        started_at="t",
        finished_at="t",
        probes_run=1,
        probes_failed=1,
        cleanup={"attempted": False, "succeeded": True, "cleanup_manifest": None},
        results=[ProbeResult(probe_id="cors_put_preflight", family="cors", status="FAIL", mismatches=[mismatch])],
    )


def test_questionnaire_includes_feature_and_mismatch_questions():
    questionnaire = generate_questionnaire(_profile(), _results().results[0].mismatches)
    questions = [item.question for item in questionnaire.questions]
    assert "Are presigned URLs used by external users, partners, browsers, or batch integrations?" in questions
    assert "Which browser origins, methods, and headers must be supported?" in questions


def test_policy_evaluate_reports_missing_hints_and_overrides():
    policy = load_policy("policy-packs/application-uploads.yml")
    evaluation = evaluate_policy(policy, _profile(), _results())
    assert evaluation.status == "FAIL"
    assert evaluation.evidence_policy_status == "REVIEW"
    assert evaluation.target_policy_status == "FAIL"
    assert "metadata_headers" in evaluation.missing_required_hints
    assert evaluation.severity_overrides_applied["CORS_PREFLIGHT_MISMATCH"] == "BLOCKER"
    assert evaluation.blocker_mismatch_codes == ["CORS_PREFLIGHT_MISMATCH"]


def test_matrix_builds_multi_target_summary(tmp_path):
    profile_path = tmp_path / "usage-profile.json"
    results_path = tmp_path / "probe-results.json"
    write_json(profile_path, _profile())
    write_json(results_path, _results())
    matrix = build_matrix(profile_path, [results_path])
    assert matrix.target_count == 1
    assert matrix.targets[0].compatibility_status == "FAIL"
    assert matrix.targets[0].top_codes == ["CORS_PREFLIGHT_MISMATCH"]


def test_cli_validation_schema_questionnaire_policy_and_matrix(tmp_path):
    profile_path = tmp_path / "usage-profile.json"
    results_path = tmp_path / "probe-results.json"
    write_json(profile_path, _profile())
    write_json(results_path, _results())
    runner = CliRunner()
    validate_result = runner.invoke(app, ["validate", str(profile_path), "--type", "usage-profile", "--strict"])
    assert validate_result.exit_code == 0, validate_result.output
    schema_result = runner.invoke(app, ["schema", "usage-profile"])
    assert schema_result.exit_code == 0, schema_result.output
    question_result = runner.invoke(app, ["questionnaire", "generate", "--profile", str(profile_path), "--output", str(tmp_path / "questions.yml")])
    assert question_result.exit_code == 0, question_result.output
    policy_result = runner.invoke(app, ["policy", "evaluate", "--policy", "policy-packs/application-uploads.yml", "--profile", str(profile_path), "--results", str(results_path), "--output", str(tmp_path / "policy.json")])
    assert policy_result.exit_code == 0, policy_result.output
    matrix_result = runner.invoke(app, ["compare-results", "--profile", str(profile_path), "--results", str(results_path), "--output-matrix", str(tmp_path / "matrix.json")])
    assert matrix_result.exit_code == 0, matrix_result.output
    assert json.loads((tmp_path / "matrix.json").read_text(encoding="utf-8"))["target_count"] == 1
