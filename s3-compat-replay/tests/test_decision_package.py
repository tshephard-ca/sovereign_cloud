from __future__ import annotations

import csv
import json

from typer.testing import CliRunner

from s3_compat_replay.cli import app
from s3_compat_replay.decision import build_cutover_brief
from s3_compat_replay.models import Mismatch, OperationFamilyProfile, Probe, ProbePlan, ProbeResult, ProbeResults, ProbeStep, UsageProfile
from s3_compat_replay.probe_plan import plan_to_yaml
from s3_compat_replay.report import build_summary, write_json

from conftest import make_event, write_records


def _profile() -> UsageProfile:
    return UsageProfile(
        source_bucket="bucket_001",
        event_count=20,
        processed_event_count=20,
        operation_families={
            "object_read": OperationFamilyProfile(count=10, event_names={"GetObject": 10}),
            "cors": OperationFamilyProfile(count=5, event_names={"GetBucketCors": 5}),
        },
        observed_features=["CORS", "PRESIGNED_OBSERVED"],
        request_hint_features=["CORS", "PRESIGNED_OBSERVED"],
    )


def _plan() -> ProbePlan:
    return ProbePlan(
        source_bucket="bucket_001",
        generated_at="2026-01-01T00:00:00Z",
        scratch_prefix="compat-replay/",
        safety={"uses_synthetic_objects_only": True},
        probes=[
            Probe(id="cors_put_preflight", family="cors", required=True, steps=[ProbeStep(operation="CorsPreflight")]),
            Probe(id="presigned_get", family="presigned", required=True, steps=[ProbeStep(operation="PresignedUrl")]),
        ],
    )


def _results() -> ProbeResults:
    mismatch = Mismatch(
        severity="BLOCKER",
        probe_id="cors_put_preflight",
        operation_family="cors",
        operation="CorsPreflight",
        evidence_source="REQUEST_HINTS",
        expected="CORS allow headers present",
        actual="headers absent",
        mismatch_code="CORS_PREFLIGHT_MISMATCH",
        reason_text="Target did not return expected CORS allow headers.",
        business_impact="Browser flows may fail even if server-side SDK traffic works.",
        suggested_human_question="Which browser origins, methods, and headers must be supported?",
    )
    return ProbeResults(
        run_id="run",
        endpoint_url_redacted="https://endpoint_redacted",
        target_bucket_redacted="bucket_002",
        scratch_prefix="compat-replay/",
        started_at="t",
        finished_at="t",
        probes_run=2,
        probes_failed=1,
        cleanup={"attempted": True, "succeeded": True, "cleanup_manifest": None},
        results=[
            ProbeResult(probe_id="cors_put_preflight", family="cors", status="FAIL", severity="BLOCKER", mismatches=[mismatch]),
            ProbeResult(probe_id="presigned_get", family="presigned", status="PASS"),
        ],
    )


def test_cutover_brief_blocks_cutover_and_groups_owner_questions():
    profile = _profile()
    plan = _plan()
    results = _results()
    summary = build_summary(profile, results)
    brief = build_cutover_brief(profile, plan, results, summary)
    assert brief.cutover_recommendation == "BLOCK"
    assert brief.target_semantic_status == "FAIL"
    assert brief.blockers[0].owner_role == "web product owner"
    assert brief.capability_ledger
    assert brief.owner_questions[0].blocks_cutover_if_unanswered is True


def test_preflight_package_writes_decision_artifacts(tmp_path):
    cloudtrail = write_records(tmp_path / "events.json", [make_event("GetObject"), make_event("GetBucketCors", key=None)])
    results_path = tmp_path / "probe-results.json"
    write_json(results_path, _results())
    output_dir = tmp_path / "preflight"
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            "package",
            "--cloudtrail",
            str(cloudtrail),
            "--source-bucket",
            "source-bucket-example",
            "--results",
            str(results_path),
            "--output-dir",
            str(output_dir),
            "--redact",
        ],
    )
    assert result.exit_code == 0, result.output
    brief = json.loads((output_dir / "cutover-brief.json").read_text(encoding="utf-8"))
    assert brief["cutover_recommendation"] == "BLOCK"
    assert (output_dir / "cutover-brief.md").exists()
    assert (output_dir / "capability-ledger.csv").exists()
    assert (output_dir / "remediation-queue.csv").exists()
    with (output_dir / "remediation-queue.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["business_flow"] == "browser upload/download"


def test_schema_supports_cutover_brief():
    result = CliRunner().invoke(app, ["schema", "cutover-brief"])
    assert result.exit_code == 0, result.output
    assert "cutover_recommendation" in result.output
