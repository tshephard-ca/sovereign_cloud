import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from stateful_storage_fit.cli import app
from stateful_storage_fit.governance import audit_manifest, decision_diff, path_purpose_template, quality_gate
from stateful_storage_fit.workflow import build_manifest

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
        commands=[],
        collector_version="test",
        redaction_mode="none",
        safe_host_facts={"system": "test"},
    )
    _write(bundle / "manifest.json", json.dumps(manifest))
    return bundle


def test_path_purpose_template_marks_owner_required(tmp_path):
    data = path_purpose_template(_bundle(tmp_path))
    assert data["paths"]
    data_path = next(path for path in data["paths"] if path["path"] == "/data")
    assert data_path["purpose"] == "owner_required"
    assert data_path["owner_confidence"] == "REQUIRES_OWNER"


def test_quality_gate_blocks_generic_profile_and_low_topology(tmp_path):
    input_report = _write(
        tmp_path / "input.json",
        json.dumps(
            {
                "valid": True,
                "warnings": ["PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC"],
                "bundle_validation": {
                    "core_completeness_score": 1.0,
                    "topology_completeness_score": 0.4,
                    "overall_bundle_quality_score": 0.8,
                },
            }
        ),
    )
    decision_report = _write(tmp_path / "decision.json", json.dumps({"valid": True, "issues": []}))
    gate = quality_gate(input_realism=input_report, decision_validation=decision_report)
    assert gate["gate_status"] == "REVIEW"
    assert "TOPOLOGY_EVIDENCE_BELOW_GATE" in gate["issues"]
    assert "GENERIC_PROFILE_BLOCKED_FOR_BUSINESS_REVIEW" in gate["issues"]


def test_decision_diff_and_audit_manifest(tmp_path):
    old = _write(
        tmp_path / "old.json",
        json.dumps({"fit_status": "PASS", "warnings": [], "reason_codes": ["STORAGE_CLASS_MATCH"], "blockers": []}),
    )
    new = _write(
        tmp_path / "new.json",
        json.dumps({"fit_status": "REVIEW", "warnings": ["IOSTAT_MISSING"], "reason_codes": ["IOSTAT_MISSING"], "blockers": []}),
    )
    diff = decision_diff(old, new)
    assert diff["changed"]
    assert diff["scalar_changes"][0]["field"] == "fit_status"
    manifest = audit_manifest(tmp_path)
    assert manifest["file_count"] >= 2
    assert manifest["audit_fingerprint"]


def test_cli_governance_commands_and_run_audit(tmp_path):
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

    commands = [
        ["tool-preflight"],
        ["evidence-modes"],
        ["path-purpose-template", "--bundle", str(bundle)],
    ]
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output

    audit_dir = tmp_path / "audit"
    result = runner.invoke(
        app,
        [
            "run-audit",
            "--output-dir",
            str(audit_dir),
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
            "--case-id",
            "audit-001",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (audit_dir / "fit.json").exists()
    assert (audit_dir / "quality-gate.json").exists()
    assert json.loads((audit_dir / "decision-validation.json").read_text(encoding="utf-8"))["valid"]

    result = runner.invoke(app, ["coverage-plan", "--corpus-dir", "examples/corpus"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["requests"]

    result = runner.invoke(app, ["business-impact-summary", "--corpus-dir", str(audit_dir / "corpus")])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["claim_status"] == "EVIDENCE_MISSING"

    result = runner.invoke(app, ["evidence-questions", "--decision", str(audit_dir / "fit.json")])
    assert result.exit_code == 0, result.output
    assert "question_count" in json.loads(result.output)

    terms = _write(tmp_path / "terms.txt", "forbidden-example\n")
    result = runner.invoke(app, ["proprietary-scan", "--path", str(audit_dir), "--banned-terms", str(terms)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["valid"]


def test_full_coverage_lab_generator_quick_mode(tmp_path):
    lab = tmp_path / "lab"
    result = runner.invoke(app, ["generate-full-coverage-lab", "--output-dir", str(lab), "--quick"])
    assert result.exit_code == 0, result.output
    summary = json.loads((lab / "full-coverage-lab-summary.json").read_text(encoding="utf-8"))
    assert summary["data_origin"] == "generated_full_coverage"
    assert summary["case_count"] == 6
    assert (lab / "storage-profile.yml").exists()
    assert len(list((lab / "corpus").glob("*.yml"))) == 6

    result = runner.invoke(app, ["business-impact-summary", "--corpus-dir", str(lab / "corpus")])
    assert result.exit_code == 0, result.output
    impact = json.loads(result.output)
    assert impact["impact_record_count"] == 6
    assert impact["claim_status"] == "SIMULATED_ONLY"


def test_gap_closure_lab_covers_hard_failures_and_boundaries(tmp_path):
    lab = tmp_path / "gap-lab"
    result = runner.invoke(app, ["generate-gap-closure-lab", "--output-dir", str(lab)])
    assert result.exit_code == 0, result.output
    summary = json.loads((lab / "gap-closure-summary.json").read_text(encoding="utf-8"))
    assert summary["closed_gap_count"] == 85
    assert summary["fit_status_counts"]["FAIL"] >= 4
    assert "SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE" in summary["blockers_observed"]
    assert "RAW_BLOCK_REQUIRED_NO_PROFILE" in summary["blockers_observed"]
    assert "CAPACITY_EXCEEDS_AVAILABLE_PROFILE" in summary["blockers_observed"]
    assert "CAPACITY_RISK_MEDIUM" in summary["reason_codes_observed"]
    assert "LATENCY_RISK_MEDIUM" in summary["reason_codes_observed"]
    assert "LOW_LATENCY_STORAGE_RECOMMENDED" in summary["reason_codes_observed"]
    assert "IOSTAT_PARSE_FAILED" in summary["reason_codes_observed"]
    assert (lab / "real-evidence-requirements" / "real-world-evidence-contract.yml").exists()
    assert (lab / "audit-manifest.local-hmac-signature.json").exists()

    capacity_case = yaml.safe_load((lab / "corpus" / "capacity-exceeds-profile-fail.yml").read_text(encoding="utf-8"))
    decision = capacity_case["engine_decision"]
    assert decision["capacity_risk"] == "HIGH"
    assert "CAPACITY_RISK_HIGH" in decision["reason_codes"]
    assert "CAPACITY_RISK_LOW" not in decision["reason_codes"]


def test_operational_gap_closure_commands(tmp_path):
    bundle = _bundle(tmp_path)
    profile = _write(tmp_path / "profile.yml", PROFILE)
    audit_dir = tmp_path / "audit"
    result = runner.invoke(
        app,
        [
            "run-audit",
            "--output-dir",
            str(audit_dir),
            "--bundle",
            str(bundle),
            "--storage-profile",
            str(profile),
            "--app-name",
            "inventory",
            "--workload-family",
            "relational_database",
            "--case-id",
            "audit-ops",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["owner-evidence-template", "--bundle", str(bundle)])
    assert result.exit_code == 0, result.output
    owner_template = yaml.safe_load(result.output)
    assert "growth_and_retention" in owner_template

    result = runner.invoke(app, ["attestation-template", "--kind", "profile", "--subject", "profile.yml"])
    assert result.exit_code == 0, result.output
    attestation = yaml.safe_load(result.output)
    assert attestation["claims"]["profile_matches_target_platform"]

    result = runner.invoke(
        app,
        [
            "trend-report",
            "--decision",
            str(audit_dir / "fit.json"),
            "--decision",
            str(audit_dir / "fit.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["decision_count"] == 2

    result = runner.invoke(app, ["followup-sla", "--corpus-dir", str(audit_dir / "corpus")])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["item_count"] >= 1

    zip_path = tmp_path / "handoff.zip"
    result = runner.invoke(app, ["handoff-bundle", "--audit-dir", str(audit_dir), "--output", str(zip_path)])
    assert result.exit_code == 0, result.output
    assert zip_path.exists()
    assert json.loads(result.output)["output"] == str(zip_path)


def test_evidence_contract_attestation_and_custody_commands(tmp_path):
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    _write(audit_dir / "fit.json", json.dumps({"fit_status": "REVIEW"}))
    key = _write(tmp_path / "key.txt", "test-key\n")

    result = runner.invoke(app, ["real-world-evidence-contract"])
    assert result.exit_code == 0, result.output
    contract = yaml.safe_load(result.output)
    assert "required_for_calibration" in contract

    result = runner.invoke(app, ["operating-model-template"])
    assert result.exit_code == 0, result.output
    assert "workload_owner" in yaml.safe_load(result.output)["roles"]

    attestation = tmp_path / "attestation.yml"
    result = runner.invoke(app, ["attestation-template", "--kind", "profile", "--output", str(attestation)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["validate-attestation", "--attestation", str(attestation), "--expected-kind", "profile"])
    assert result.exit_code == 0, result.output
    assert not json.loads(result.output)["valid"]

    manifest = tmp_path / "manifest.json"
    result = runner.invoke(app, ["audit-manifest", "--audit-dir", str(audit_dir), "--output", str(manifest)])
    assert result.exit_code == 0, result.output
    signature = tmp_path / "signature.json"
    result = runner.invoke(app, ["sign-audit-manifest", "--manifest", str(manifest), "--key-file", str(key), "--output", str(signature)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["verify-audit-signature", "--signature", str(signature), "--key-file", str(key)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["valid"]

    result = runner.invoke(app, ["evidence-repository-export", "--audit-dir", str(audit_dir)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["repository_contract"]["network_calls_performed"] is False

    result = runner.invoke(app, ["chain-of-custody", "--audit-dir", str(audit_dir)])
    assert result.exit_code == 0, result.output
    assert "EXTERNAL_TIMESTAMP_REFERENCE_MISSING" in json.loads(result.output)["warnings"]
