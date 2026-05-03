from __future__ import annotations

import json
import zipfile

from s3_compat_replay.bundle import create_case_bundle, read_bundle_artifacts, validate_case_bundle
from s3_compat_replay.corpus import summarize_corpus, import_bundle
from s3_compat_replay.models import OperationFamilyProfile, Probe, ProbePlan, ProbeResult, ProbeResults, ProbeStep, UsageProfile
from s3_compat_replay.probe_plan import plan_to_yaml
from s3_compat_replay.report import write_json, write_mismatches_csv


def _artifacts(tmp_path):
    profile = UsageProfile(
        source_bucket="sensitive-source-bucket",
        event_count=2500,
        processed_event_count=2500,
        operation_families={
            "object_read": OperationFamilyProfile(count=100, event_names={"GetObject": 100}),
            "object_write": OperationFamilyProfile(count=20, event_names={"PutObject": 20}),
        },
        observed_features=["CORS", "PRESIGNED_OBSERVED"],
        request_hint_features=["CORS", "PRESIGNED_OBSERVED"],
        user_agents=["custom-sdk/1.0"],
    )
    plan = ProbePlan(
        source_bucket="sensitive-source-bucket",
        generated_at="2026-01-01T00:00:00Z",
        probes=[Probe(id="head_missing", family="object_read", steps=[ProbeStep(operation="HeadObject", key_suffix="missing.txt", expect={"status": 404})])],
    )
    results = ProbeResults(
        run_id="run",
        endpoint_url_redacted="https://real-target.internal.example/path",
        target_bucket_redacted="sensitive-target-bucket",
        scratch_prefix="compat-replay/",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
        probes_run=1,
        cleanup={"attempted": False, "succeeded": True, "cleanup_manifest": None},
        results=[ProbeResult(probe_id="head_missing", family="object_read")],
    )
    profile_path = tmp_path / "usage-profile.json"
    plan_path = tmp_path / "probe-plan.yml"
    results_path = tmp_path / "probe-results.json"
    mismatches_path = tmp_path / "mismatches.csv"
    write_json(profile_path, profile)
    plan_path.write_text(plan_to_yaml(plan), encoding="utf-8")
    write_json(results_path, results)
    write_mismatches_csv(mismatches_path, results)
    return profile_path, plan_path, results_path, mismatches_path


def test_case_bundle_create_and_validate(tmp_path):
    profile, plan, results, mismatches = _artifacts(tmp_path)
    output = tmp_path / "case-bundle.zip"
    manifest, report = create_case_bundle(profile_path=profile, plan_path=plan, results_path=results, mismatches_path=mismatches, output_path=output, workload_type="application_upload_bucket")
    assert output.exists()
    assert manifest.workload_type == "application_upload_bucket"
    assert report.redaction_status == "PASS"
    artifacts = read_bundle_artifacts(output)
    assert "case.yml" in artifacts
    assert "redaction-report.json" in artifacts
    assert "sensitive-source-bucket" not in "\n".join(artifacts.values())
    ok, errors, validate_report = validate_case_bundle(output, strict_redaction=True)
    assert ok, errors
    assert validate_report.redaction_status == "PASS"


def test_corpus_import_and_summarize(tmp_path):
    profile, plan, results, mismatches = _artifacts(tmp_path)
    bundle = tmp_path / "case-bundle.zip"
    create_case_bundle(profile_path=profile, plan_path=plan, results_path=results, mismatches_path=mismatches, output_path=bundle)
    imported = import_bundle(bundle, tmp_path / "corpus")
    assert imported.exists()
    summary = summarize_corpus(tmp_path / "corpus")
    assert summary.case_count == 1
    assert summary.observed_families["object_read"] == 1


def test_bundle_validate_fails_on_unredacted_host(tmp_path):
    profile, plan, results, mismatches = _artifacts(tmp_path)
    bundle = tmp_path / "case-bundle.zip"
    create_case_bundle(profile_path=profile, plan_path=plan, results_path=results, mismatches_path=mismatches, output_path=bundle)
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(broken, "w") as dst:
        for name in src.namelist():
            text = src.read(name).decode("utf-8")
            if name == "compat-summary.md":
                text += "https://unredacted.internal.example\n"
            dst.writestr(name, text)
    ok, errors, report = validate_case_bundle(broken, strict_redaction=True)
    assert not ok
    assert report.checks.endpoint_hostnames_found >= 1
