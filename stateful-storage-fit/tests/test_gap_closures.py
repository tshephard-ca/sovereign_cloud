import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from stateful_storage_fit.cli import app
from stateful_storage_fit.collector import collect_du_summary
from stateful_storage_fit.classify_mounts import classify_candidate_mounts
from stateful_storage_fit.config import DEFAULT_THRESHOLDS
from stateful_storage_fit.parse_df import parse_df_text
from stateful_storage_fit.parse_fstab import parse_fstab_text
from stateful_storage_fit.parse_iostat import parse_iostat_text
from stateful_storage_fit.parse_mount import parse_mount_text
from stateful_storage_fit.validators import validate_decision, validate_input_realism
from stateful_storage_fit.workflow import build_manifest, corpus_coverage, validate_bundle

from tests.helpers import DF_DATA, FSTAB_DATA, IOSTAT_LOW, MOUNT_DATA, PROFILE, PS_DB


runner = CliRunner()


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)
    _write(bundle / "df.txt", DF_DATA)
    _write(bundle / "mount.txt", MOUNT_DATA)
    _write(bundle / "fstab.txt", FSTAB_DATA)
    _write(bundle / "iostat.txt", IOSTAT_LOW)
    _write(bundle / "ps.txt", PS_DB)
    manifest = build_manifest(
        bundle,
        commands=[
            {"file": "blkid.txt", "command": ["blkid"], "returncode": 2, "status": "command_failed"},
        ],
        collector_version="test",
        redaction_mode="none",
        safe_host_facts={"system": "test"},
    )
    _write(bundle / "manifest.json", json.dumps(manifest))
    return bundle


def test_candidate_mounts_include_score_and_false_positive_risk():
    df, _ = parse_df_text(DF_DATA)
    mounts, _ = parse_mount_text(MOUNT_DATA)
    fstab, _ = parse_fstab_text(FSTAB_DATA)
    iostat, _, _ = parse_iostat_text(IOSTAT_LOW)
    candidates, _, _ = classify_candidate_mounts(df, mounts, fstab, iostat, DEFAULT_THRESHOLDS, [])
    data_mount = next(candidate for candidate in candidates if candidate.mount_path == "/data")
    assert data_mount.candidate_score > 0
    assert "KNOWN_DATA_PATH" in data_mount.candidate_score_reasons
    assert data_mount.ownership_confidence in {"MEDIUM", "HIGH"}
    assert data_mount.false_positive_risk in {"LOW", "MEDIUM", "HIGH"}


def test_collect_du_generates_path_scoped_summary_and_updates_manifest(tmp_path):
    bundle = _bundle(tmp_path)
    manifest = collect_du_summary(bundle, data_paths=["/srv/private-data"], redact_paths=True)
    summary = (bundle / "du-summary.txt").read_text(encoding="utf-8")
    assert "/redacted/path_001/private-data" in summary
    assert "/srv/private-data" not in summary
    assert "command_failed" in summary or "ok" in summary
    assert (bundle / "redaction-map-du.json").exists()
    assert manifest["bundle_fingerprint"]
    assert validate_bundle(bundle)["valid"]

    cli_bundle = _bundle(tmp_path / "cli")
    result = runner.invoke(
        app,
        [
            "collect-du",
            "--bundle",
            str(cli_bundle),
            "--data-path",
            "/srv/private-data",
            "--redact-paths",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (cli_bundle / "du-summary.txt").exists()


def test_validate_decision_flags_broken_redaction_and_unsupported_confidence(tmp_path):
    decision = _write(
        tmp_path / "fit.json",
        json.dumps(
            {
                "fit_status": "PASS",
                "confidence": "HIGH",
                "missing_data": ["iostat"],
                "required_access_mode": "ReadWriteOnce",
                "required_volume_mode": "Filesystem",
                "reason_codes": [],
                "blockers": [],
                "storage_request_gib": 1,
                "analysis": {
                    "evidence_graph": {
                        "observations": [
                            {"subject": "path_001"},
                        ],
                    },
                },
            }
        ),
    )
    report = validate_decision(decision)
    assert not report["valid"]
    assert "HIGH_CONFIDENCE_WITH_CRITICAL_MISSING_DATA" in report["issues"]
    assert "BROKEN_PATH_REDACTION_NON_ABSOLUTE" in report["issues"]


def test_validate_input_realism_scores_bundle_and_network_context(tmp_path):
    bundle = _bundle(tmp_path)
    _write(bundle / "mount.txt", MOUNT_DATA + "server:/exports/data on /srv/content type nfs4 (rw,relatime)\n")
    manifest = build_manifest(
        bundle,
        commands=[],
        collector_version="test",
        redaction_mode="none",
        safe_host_facts={"system": "test"},
    )
    _write(bundle / "manifest.json", json.dumps(manifest))
    profile = _write(tmp_path / "profile.yml", PROFILE)
    report = validate_input_realism(bundle_dir=bundle, storage_profile=profile)
    assert report["valid"]
    assert "PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC" in report["warnings"]
    assert report["network_filesystem_mounts"]["data_like"] == ["/srv/content"]


def test_cli_gap_commands_and_app_metadata(tmp_path):
    bundle = _bundle(tmp_path)
    profile = _write(tmp_path / "profile.yml", PROFILE)
    path_purpose = _write(
        tmp_path / "path-purpose.yml",
        yaml.safe_dump(
            {
                "paths": [
                    {
                        "path": "/data",
                        "purpose": "database data",
                        "read_write_pattern": "read_write",
                        "writer_topology": "single_writer",
                        "owner_confidence": "HIGH",
                    }
                ]
            }
        ),
    )
    output = tmp_path / "fit.json"
    result = runner.invoke(
        app,
        [
            "check",
            "--bundle",
            str(bundle),
            "--storage-profile",
            str(profile),
            "--path-purpose",
            str(path_purpose),
            "--app-name",
            "inventory",
            "--workload-family",
            "relational_database",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    decision = json.loads(output.read_text(encoding="utf-8"))
    assert "APP_DATA_PATH_DECLARED" in decision["reason_codes"]
    assert decision["evidence"]["app_metadata"]["app_name"] == "inventory"

    for command, expected in [
        (["validate-decision", "--decision", str(output)], "valid"),
        (["validate-input-realism", "--bundle", str(bundle), "--storage-profile", str(profile), "--path-purpose", str(path_purpose)], "bundle_validation"),
        (["profile-snapshot", "--storage-profile", str(profile), "--origin", "lab_export"], "fingerprint"),
    ]:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
        assert expected in json.loads(result.output)


def test_corpus_coverage_and_evaluation_comparison_commands(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    case = {
        "schema_version": "1.0",
        "id": "case-001",
        "data_origin": "synthetic",
        "lifecycle_state": "engine_analyzed",
        "storage_profile": "profile.yml",
        "app_metadata": {"workload_family": "shared_filesystem"},
        "engine_decision": {
            "fit_status": "FAIL",
            "required_access_mode": "ReadWriteMany",
            "preferred_storage_kind": "file",
            "reason_codes": ["SHARED_FS_DETECTED"],
            "blockers": ["SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE"],
        },
        "expert_reviews": [],
        "outcomes": [{"status": "blocked_by_storage"}],
    }
    _write(corpus / "case-001.yml", yaml.safe_dump(case))
    coverage = corpus_coverage(corpus)
    assert coverage["family_counts"]["shared_filesystem"] == 1
    assert coverage["capability_counts"]["rwx"] == 1

    old = _write(tmp_path / "old.json", json.dumps({"decision_accuracy": 1.0, "readiness": {"level": "CALIBRATED_INTERNAL"}}))
    new = _write(tmp_path / "new.json", json.dumps({"decision_accuracy": 0.5, "readiness": {"level": "RESEARCH_ONLY"}}))
    result = runner.invoke(app, ["compare-evaluations", "--old", str(old), "--new", str(new)])
    assert result.exit_code == 0, result.output
    comparison = json.loads(result.output)
    assert "DECISION_ACCURACY_REGRESSION" in comparison["regressions"]
