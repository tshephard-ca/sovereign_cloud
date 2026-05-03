from __future__ import annotations

import json

from typer.testing import CliRunner

from s3_compat_replay import cli
from s3_compat_replay.models import Probe, ProbePlan, ProbeStep
from s3_compat_replay.probe_plan import plan_to_yaml
from s3_compat_replay.probes import run_probe_plan

from conftest import FakeS3Client


def _plan(probes):
    return ProbePlan(
        source_bucket="source-bucket-example",
        generated_at="2026-01-01T00:00:00Z",
        scratch_prefix="compat-replay/",
        safety={"uses_synthetic_objects_only": True},
        probes=probes,
    )


def test_skips_write_probes_in_read_only_mode():
    plan = _plan([Probe(id="write", family="object_read", required=True, requires_allow_writes=True, setup=[ProbeStep(operation="PutObject", key_suffix="a.txt")], steps=[ProbeStep(operation="GetObject", key_suffix="a.txt")])])
    results, _ = run_probe_plan(plan, client=FakeS3Client(), endpoint_url="https://target.example.invalid", target_bucket="bucket", scratch_prefix="compat-replay/", read_only=True)
    assert results.results[0].status == "SKIP"
    assert "READ_ONLY_MODE_SKIPPED_WRITE_PROBES" in results.warnings


def test_requires_allow_writes_for_put_setup():
    plan = _plan([Probe(id="write", family="object_read", required=True, requires_allow_writes=True, setup=[ProbeStep(operation="PutObject", key_suffix="a.txt")])])
    results, _ = run_probe_plan(plan, client=FakeS3Client(), endpoint_url="https://target.example.invalid", target_bucket="bucket", scratch_prefix="compat-replay/")
    assert results.results[0].status == "SKIP"


def test_requires_allow_deletes_acl_multipart_and_object_lock_flags():
    probes = [
        Probe(id="delete", family="object_delete", requires_allow_deletes=True, steps=[ProbeStep(operation="DeleteObject", key_suffix="a.txt")]),
        Probe(id="acl", family="acl", requires_allow_acl_tests=True, steps=[ProbeStep(operation="GetObjectAcl", key_suffix="a.txt")]),
        Probe(id="multipart", family="multipart", requires_allow_multipart=True, steps=[ProbeStep(operation="CreateMultipartUpload", key_suffix="a.txt")]),
        Probe(id="lock", family="object_lock", requires_allow_object_lock_tests=True, steps=[ProbeStep(operation="PutObjectRetention", key_suffix="a.txt")]),
    ]
    results, _ = run_probe_plan(_plan(probes), client=FakeS3Client(), endpoint_url="https://target.example.invalid", target_bucket="bucket", scratch_prefix="compat-replay/", allow_writes=True)
    assert [result.status for result in results.results] == ["SKIP", "SKIP", "SKIP", "SKIP"]
    assert set(results.warnings) >= {"DESTRUCTIVE_PROBES_SKIPPED", "ACL_PROBES_SKIPPED", "MULTIPART_PROBES_SKIPPED", "OBJECT_LOCK_PROBES_SKIPPED"}


def test_cleanup_manifest_is_written_when_cleanup_fails():
    plan = _plan([Probe(id="write", family="object_read", required=True, requires_allow_writes=True, setup=[ProbeStep(operation="PutObject", key_suffix="a.txt", expect={"status": 200})])])
    results, manifest = run_probe_plan(plan, client=FakeS3Client(fail_cleanup=True), endpoint_url="https://target.example.invalid", target_bucket="bucket", scratch_prefix="compat-replay/", allow_writes=True, cleanup=True)
    assert results.cleanup["cleanup_manifest"] == "cleanup-manifest.json"
    assert manifest is not None
    assert manifest.reason == "CLEANUP_FAILED"


def test_cors_probe_constructs_options_request_correctly():
    plan = _plan([Probe(id="cors", family="cors", steps=[ProbeStep(operation="CorsPreflight", params={"origin": "https://app.example.invalid", "method": "PUT", "request_headers": ["Content-Type"]}, expect={"status": 200, "cors": {"origin": "https://app.example.invalid", "method": "PUT", "request_headers": ["Content-Type"]}})])])
    client = FakeS3Client()
    results, _ = run_probe_plan(plan, client=client, endpoint_url="https://target.example.invalid", target_bucket="bucket", scratch_prefix="compat-replay/", cleanup=False)
    assert results.results[0].status == "PASS"
    assert client.calls[0] == ("CorsPreflight", {"bucket": "bucket", "origin": "https://app.example.invalid", "method": "PUT", "request_headers": ["Content-Type"]})


def test_cli_probe_strict_fails_on_missing_credentials(tmp_path):
    plan_path = tmp_path / "plan.yml"
    plan_path.write_text(plan_to_yaml(_plan([])), encoding="utf-8")
    result = CliRunner().invoke(
        cli.app,
        [
            "probe",
            "--plan",
            str(plan_path),
            "--endpoint-url",
            "https://target.example.invalid",
            "--target-bucket",
            "bucket",
            "--region",
            "us-east-1",
            "--access-key-env",
            "MISSING_ACCESS",
            "--secret-key-env",
            "MISSING_SECRET",
            "--scratch-prefix",
            "compat-replay/",
            "--output-results",
            str(tmp_path / "results.json"),
            "--output-mismatches",
            str(tmp_path / "mismatches.csv"),
            "--strict",
        ],
    )
    assert result.exit_code != 0
    assert "credentials" in result.output


def test_cli_probe_uses_fake_client(monkeypatch, tmp_path):
    class Factory(FakeS3Client):
        def __init__(self, **kwargs):
            super().__init__()

    monkeypatch.setenv("TARGET_ACCESS_KEY_ID", "access")
    monkeypatch.setenv("TARGET_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(cli, "S3CompatibleClient", Factory)
    plan_path = tmp_path / "plan.yml"
    plan_path.write_text(
        plan_to_yaml(
            _plan([
                Probe(id="head_missing", family="object_read", steps=[ProbeStep(operation="HeadObject", key_suffix="missing.txt", expect={"status": 404, "error_code": "NoSuchKey"})])
            ])
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli.app,
        [
            "probe",
            "--plan",
            str(plan_path),
            "--endpoint-url",
            "https://target.example.invalid",
            "--target-bucket",
            "bucket",
            "--region",
            "us-east-1",
            "--access-key-env",
            "TARGET_ACCESS_KEY_ID",
            "--secret-key-env",
            "TARGET_SECRET_ACCESS_KEY",
            "--scratch-prefix",
            "compat-replay/",
            "--output-results",
            str(tmp_path / "results.json"),
            "--output-mismatches",
            str(tmp_path / "mismatches.csv"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["probes_run"] == 1
