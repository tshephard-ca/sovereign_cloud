import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from typer.testing import CliRunner

from estate_triage.adapters import (
    merge_evidence_sets,
    read_backup_evidence_csv,
    read_inventory_evidence_csv,
)
from estate_triage.api import analyze_csv_estate, analyze_estate
from estate_triage.assessment import RankingMode, rank_assessments
from estate_triage.cli import app
from estate_triage.evidence import (
    ASSESSMENT_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    FEATURE_SCHEMA_VERSION,
    POLICY_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
)
from estate_triage.identity import resolve_identities
from estate_triage.policy import DEFAULT_POLICY_PACK
from estate_triage.privacy import redact_assessment


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
NOW = datetime(2026, 4, 30, tzinfo=timezone.utc)


def test_public_contract_versions_are_declared():
    assert EVIDENCE_SCHEMA_VERSION == "1.0.0"
    assert FEATURE_SCHEMA_VERSION == "1.0.0"
    assert POLICY_SCHEMA_VERSION == "1.0.0"
    assert ASSESSMENT_SCHEMA_VERSION == "1.0.0"
    assert TRACE_SCHEMA_VERSION == "1.0.0"
    assert DEFAULT_POLICY_PACK.id == "default"
    assert DEFAULT_POLICY_PACK.version == "1.0.0"
    assert DEFAULT_POLICY_PACK.approved_by == "project-maintainers"
    assert DEFAULT_POLICY_PACK.compatible_schema_versions["feature"] == FEATURE_SCHEMA_VERSION


def test_adapters_emit_canonical_evidence_with_provenance():
    result = read_inventory_evidence_csv(EXAMPLES / "inventory.csv")

    record = result.evidence.records[0]
    assert result.evidence.schema_version == EVIDENCE_SCHEMA_VERSION
    assert record.source_type == "inventory"
    assert record.fields["name"].source_ref.row_number == 2
    assert record.fields["memory_mib"].unit == "MiB"
    assert record.fields["normalized_name"].value == "mig-payments-api"


def test_identity_resolution_exposes_uuid_name_conflict(tmp_path):
    inventory = tmp_path / "inventory.csv"
    backup = tmp_path / "backup.csv"
    inventory.write_text(
        "VM,VM UUID\nshared-name,uuid-a\n",
        encoding="utf-8",
    )
    backup.write_text(
        "VM,VM UUID,backup_total_mib\n"
        "shared-name,uuid-b,100\n"
        "other-name,uuid-a,100\n",
        encoding="utf-8",
    )

    evidence = merge_evidence_sets(
        read_inventory_evidence_csv(inventory).evidence,
        read_backup_evidence_csv(backup).evidence,
    )
    result = resolve_identities(evidence)

    assert result.workloads[0].status == "CONFLICTED"
    assert result.workloads[0].matched_by == "UUID"
    assert result.workloads[0].trace.strategy == "uuid_preferred_over_conflicting_name"
    assert result.workloads[0].data_quality[0].code == "UUID_NAME_CONFLICT"


def test_identity_resolution_flags_duplicate_inventory_uuid(tmp_path):
    inventory = tmp_path / "inventory.csv"
    backup = tmp_path / "backup.csv"
    inventory.write_text(
        "VM,VM UUID\nfirst,uuid-a\nsecond,uuid-a\n",
        encoding="utf-8",
    )
    backup.write_text(
        "VM,VM UUID,backup_total_mib\nfirst,uuid-a,100\n",
        encoding="utf-8",
    )

    evidence = merge_evidence_sets(
        read_inventory_evidence_csv(inventory).evidence,
        read_backup_evidence_csv(backup).evidence,
    )
    result = resolve_identities(evidence)

    assert result.duplicate_candidates == 2
    assert {finding.code for finding in result.data_quality} >= {"DUPLICATE_INVENTORY_UUID"}
    assert {finding.code for workload in result.workloads for finding in workload.data_quality} >= {
        "DUPLICATE_INVENTORY_UUID"
    }


def test_identity_override_resolves_known_rename(tmp_path):
    inventory = tmp_path / "inventory.csv"
    backup = tmp_path / "backup.csv"
    overrides = tmp_path / "identity-overrides.yml"
    inventory.write_text(
        "VM,VM UUID,In Use MiB,OS\nnew-name,uuid-new,100,Generic Linux\n",
        encoding="utf-8",
    )
    backup.write_text(
        "VM,backup_total_mib,latest_restore_point_utc,avg_daily_change_mib\n"
        "old-name,200,2026-04-25T00:00:00Z,1\n",
        encoding="utf-8",
    )
    overrides.write_text(
        yaml.safe_dump(
            {
                "overrides": [
                    {
                        "inventory_uuid": "uuid-new",
                        "backup_name": "old-name",
                        "reason": "Known rename reviewed by local operator.",
                        "approved_by": "reviewer",
                        "approved_at_utc": "2026-04-30T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assessment = analyze_csv_estate(
        inventory_path=inventory,
        backup_path=backup,
        identity_overrides_path=overrides,
        now=NOW,
    )
    workload = assessment.workloads[0]

    assert workload.identity.trace.strategy == "identity_override"
    assert workload.identity.matched_by == "NAME"
    assert workload.identity.backup is not None
    assert {finding.code for finding in workload.data_quality} >= {"IDENTITY_OVERRIDE_APPLIED"}


def test_controlled_fuzzy_name_match_and_identity_graph_export(tmp_path):
    inventory = tmp_path / "inventory.csv"
    backup = tmp_path / "backup.csv"
    graph = tmp_path / "identity-graph.json"
    inventory.write_text(
        "VM,In Use MiB\napp-prod-01,100\n",
        encoding="utf-8",
    )
    backup.write_text(
        "VM,backup_total_mib\napp_prod_01.example.local,200\n",
        encoding="utf-8",
    )

    assessment = analyze_csv_estate(
        inventory_path=inventory,
        backup_path=backup,
        now=NOW,
    )
    workload = assessment.workloads[0]
    graph_result = CliRunner().invoke(
        app,
        [
            "identity-graph",
            "--inventory",
            str(inventory),
            "--backup",
            str(backup),
            "--output",
            str(graph),
        ],
    )

    assert workload.identity.trace.strategy == "controlled_relaxed_name"
    assert workload.identity.trace.confidence_factors["context"] == "relaxed_name_only"
    assert workload.identity.trace.field_summary
    assert {finding.code for finding in workload.data_quality} >= {"CONTROLLED_FUZZY_NAME_MATCH"}
    assert graph_result.exit_code == 0, graph_result.output
    payload = json.loads(graph.read_text(encoding="utf-8"))
    assert payload["edges"][0]["strategy"] == "controlled_relaxed_name"
    assert payload["edges"][0]["confidence_factors"]["identifier"] == "weak"


def test_validation_flags_contradictory_storage_and_percent_ranges(tmp_path):
    inventory = tmp_path / "inventory.csv"
    output = tmp_path / "validation.json"
    inventory.write_text(
        "VM,VM UUID,Provisioned MiB,In Use MiB,CPU usage percent\n"
        "contradictory,uuid-a,100,200,135%\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "validate",
            "--input",
            str(inventory),
            "--kind",
            "inventory",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    codes = {finding["code"] for finding in payload["data_quality"]}
    assert codes >= {"IN_USE_EXCEEDS_PROVISIONED", "PERCENT_OUT_OF_RANGE"}


def test_validation_profiles_mixed_formats_and_mapping_suspicion(tmp_path):
    inventory = tmp_path / "inventory.csv"
    output = tmp_path / "validation.json"
    rows = [
        "VM,VM UUID,Powerstate,Memory MiB,Last seen date",
        "same-name,uuid-001,state-001,1 GiB,2026-04-01",
        "same-name,uuid-002,state-002,2048 MiB,13/04/2026",
        "same-name,uuid-003,state-003,3 GiB,2026-04-03",
        "same-name,uuid-004,state-004,4096 MiB,13/04/2026",
        "same-name,uuid-005,state-005,5 GiB,2026-04-05",
        "same-name,uuid-006,state-006,6144 MiB,13/04/2026",
        "same-name,uuid-007,state-007,7 GiB,2026-04-07",
        "same-name,uuid-008,state-008,8192 MiB,13/04/2026",
        "same-name,uuid-009,state-009,9 GiB,2026-04-09",
        "same-name,uuid-010,state-010,10240 MiB,13/04/2026",
    ]
    inventory.write_text("\n".join(rows) + "\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "validate",
            "--input",
            str(inventory),
            "--kind",
            "inventory",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    codes = {finding["code"] for finding in payload["data_quality"]}
    name_profile = next(profile for profile in payload["field_profiles"] if profile["field"] == "name")
    memory_profile = next(profile for profile in payload["field_profiles"] if profile["field"] == "memory_mib")
    assert codes >= {"MIXED_UNITS", "MIXED_DATE_FORMATS", "LOW_CARDINALITY_IDENTIFIER"}
    assert "HIGH_CARDINALITY_CATEGORY" in codes
    assert name_profile["mapping_confidence"] == "low"
    assert memory_profile["detected_units"] == ["gib", "mib"]
    assert payload["business_severity_counts"]


def test_validation_suggests_mapping_alternatives_and_records_approval(tmp_path):
    inventory = tmp_path / "inventory.csv"
    mapping = tmp_path / "mapping.yml"
    output = tmp_path / "validation.json"
    inventory.write_text(
        "Worklod Name,VM UUID,Memory MiB\napp-001,uuid-001,4096\n",
        encoding="utf-8",
    )
    mapping.write_text(
        yaml.safe_dump(
            {
                "source_kind": "inventory",
                "columns": {
                    "uuid": "VM UUID",
                    "memory_mib": "Memory MiB",
                },
                "approved_by": "reviewer",
                "approved_at_utc": "2026-04-30T00:00:00Z",
                "approval_notes": "Reviewed during test.",
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "validate",
            "--input",
            str(inventory),
            "--kind",
            "inventory",
            "--mapping",
            str(mapping),
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mapping_approval"]["approved"] is True
    assert payload["mapping_approval"]["approved_by"] == "reviewer"
    assert any(
        alternative["field"] == "name"
        and alternative["candidate_header"] == "Worklod Name"
        for alternative in payload["mapping_alternatives"]
    )


def test_validation_fails_when_mapping_references_missing_columns(tmp_path):
    inventory = tmp_path / "inventory.csv"
    mapping = tmp_path / "mapping.yml"
    inventory.write_text("VM,VM UUID\napp-001,uuid-001\n", encoding="utf-8")
    mapping.write_text(
        yaml.safe_dump(
            {
                "source_kind": "inventory",
                "columns": {
                    "name": "VM",
                    "uuid": "Missing UUID Column",
                },
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "validate",
            "--input",
            str(inventory),
            "--kind",
            "inventory",
            "--mapping",
            str(mapping),
        ],
    )

    assert result.exit_code == 1
    assert "Mapping references columns not present" in result.output


def test_kernel_api_returns_feature_and_policy_traces():
    assessment = analyze_csv_estate(
        inventory_path=EXAMPLES / "inventory.csv",
        backup_path=EXAMPLES / "backup_export.csv",
        now=NOW,
    )

    first = assessment.workloads[0]
    assert first.schema_version == ASSESSMENT_SCHEMA_VERSION
    assert first.feature_set.features["change_rate_pct"].trace
    assert first.feature_set.features["change_rate_pct"].source_refs
    assert any(trace.fired for trace in first.winning_motion.rule_traces)
    assert first.policy_evaluation.policy_id == "default"


def test_feature_engine_exposes_context_storage_and_data_quality_features(tmp_path):
    inventory = tmp_path / "inventory.csv"
    backup = tmp_path / "backup.csv"
    inventory.write_text(
        "VM,VM UUID,Provisioned MiB,In Use MiB,Snapshot total MiB,Datacenter,Cluster,Host,Tags,Notes\n"
        "context-app,uuid-context,200,100,25,region-a,cluster-a,host-a,env:prod,reviewed\n",
        encoding="utf-8",
    )
    backup.write_text(
        "VM,VM UUID,backup_total_mib,latest_restore_point_utc,avg_daily_change_mib,backup_policy,retention_days,rpo_hours,rto_tier\n"
        "context-app,uuid-context,300,2026-04-25T00:00:00Z,1,policy-standard,30,24,standard\n",
        encoding="utf-8",
    )

    assessment = analyze_csv_estate(
        inventory_path=inventory,
        backup_path=backup,
        now=NOW,
    )
    features = assessment.workloads[0].feature_set

    assert features.value("provisioned_to_used_ratio") == 2
    assert features.value("snapshot_to_used_ratio") == 0.25
    assert features.value("application_context_present") is True
    assert features.value("protection_policy_context_present") is True
    assert features.value("data_quality_finding_count") == 0
    assert features.value("data_quality_risk") == "low"
    assert features.confidence_summary["none"] > 0


def test_feature_engine_marks_data_quality_risk(tmp_path):
    inventory = tmp_path / "inventory.csv"
    backup = tmp_path / "backup.csv"
    inventory.write_text(
        "VM,VM UUID,Provisioned MiB,In Use MiB\n"
        "bad-storage,uuid-bad,100,200\n",
        encoding="utf-8",
    )
    backup.write_text(
        "VM,VM UUID,backup_total_mib\n"
        "bad-storage,uuid-bad,300\n",
        encoding="utf-8",
    )

    assessment = analyze_csv_estate(
        inventory_path=inventory,
        backup_path=backup,
        now=NOW,
    )
    features = assessment.workloads[0].feature_set

    assert features.value("data_quality_finding_count") >= 1
    assert features.value("data_quality_risk") == "medium"
    assert features.confidence_summary["lowers_confidence"] > 0


def test_policy_uses_recency_rpo_and_utilization_window_features(tmp_path):
    inventory = tmp_path / "inventory.csv"
    backup = tmp_path / "backup.csv"
    utilization = tmp_path / "utilization.csv"
    inventory.write_text(
        "VM,VM UUID,Powerstate,CPUs,Memory MiB,In Use MiB,Last seen date\n"
        "recency-rpo,uuid-recency,poweredOff,8,32768,100000,2025-12-01\n",
        encoding="utf-8",
    )
    backup.write_text(
        "VM,VM UUID,backup_total_mib,latest_restore_point_utc,rpo_hours\n"
        "recency-rpo,uuid-recency,500000,2026-04-25T00:00:00Z,48\n",
        encoding="utf-8",
    )
    utilization.write_text(
        "VM,VM UUID,sample_start_utc,sample_end_utc,cpu_p95_pct,memory_p95_pct,sample_count\n"
        "recency-rpo,uuid-recency,2026-04-01T00:00:00Z,2026-04-01T06:00:00Z,3,20,2\n",
        encoding="utf-8",
    )

    assessment = analyze_csv_estate(
        inventory_path=inventory,
        backup_path=backup,
        utilization_path=utilization,
        now=NOW,
    )
    workload = assessment.workloads[0]
    reason_codes = {
        code
        for motion in workload.policy_evaluation.motion_assessments
        for code in motion.reason_codes
    }
    rightsizing = next(
        motion
        for motion in workload.policy_evaluation.motion_assessments
        if motion.motion == "RIGHTSIZING_REVIEW"
    )

    assert workload.feature_set.value("stale_inventory_seen") is True
    assert workload.feature_set.value("long_rpo_review") is True
    assert reason_codes >= {"STALE_INVENTORY_SEEN", "RPO_REVIEW", "SPARSE_UTILIZATION_WINDOW"}
    assert "SPARSE_UTILIZATION_WINDOW" in rightsizing.blocking_flags
    assert workload.confidence_factors["metrics"] in {"sufficient", "insufficient"}
    assert any(request.priority == "high" for request in workload.missing_evidence)


def test_analyze_estate_accepts_canonical_evidence_sets():
    inventory = read_inventory_evidence_csv(EXAMPLES / "inventory.csv")
    backup = read_backup_evidence_csv(EXAMPLES / "backup_export.csv")

    assessment = analyze_estate(
        evidence_sources=[inventory.evidence, backup.evidence],
        now=NOW,
    )

    assert assessment.input["inventory_rows"] == 25
    assert assessment.input["backup_rows"] == 25
    assert assessment.workloads


def test_ranking_modes_include_top_per_motion():
    assessment = analyze_csv_estate(
        inventory_path=EXAMPLES / "inventory.csv",
        backup_path=EXAMPLES / "backup_export.csv",
        now=NOW,
    )

    ranked = rank_assessments(assessment, top_n=1, mode=RankingMode.PER_MOTION)
    motions = {row.primary_motion for row in ranked}

    assert "MIGRATION_REVIEW" in motions
    assert "DR_TIER_REVIEW" in motions


def test_balanced_ranking_keeps_top_n_total_and_spreads_motions():
    assessment = analyze_csv_estate(
        inventory_path=EXAMPLES / "inventory.csv",
        backup_path=EXAMPLES / "backup_export.csv",
        now=NOW,
    )

    ranked = rank_assessments(assessment, top_n=8, mode=RankingMode.BALANCED)
    motions = {row.primary_motion for row in ranked}

    assert len(ranked) == 8
    assert len(motions) > 1


def test_redacted_assessment_hides_workload_names():
    assessment = analyze_csv_estate(
        inventory_path=EXAMPLES / "inventory.csv",
        backup_path=EXAMPLES / "backup_export.csv",
        now=NOW,
    )

    redacted = redact_assessment(assessment, salt="test")
    dumped = json.dumps(redacted.model_dump(mode="json"))

    assert "mig-payments-api" not in dumped
    assert "inv-uuid-001" not in dumped
    assert redacted.workloads[0].workload_name.startswith("workload_")
    assert len(redacted.workloads[0].workload_key) == 12


def test_cli_writes_structured_assessment_json(tmp_path):
    output = tmp_path / "top.csv"
    assessment_json = tmp_path / "assessment.json"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--inventory",
            str(EXAMPLES / "inventory.csv"),
            "--backup",
            str(EXAMPLES / "backup_export.csv"),
            "--output",
            str(output),
            "--assessment-json",
            str(assessment_json),
            "--top-n",
            "3",
            "--redact",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(assessment_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == ASSESSMENT_SCHEMA_VERSION
    assert "mig-payments-api" not in assessment_json.read_text(encoding="utf-8")
    assert "inv-uuid-001" not in assessment_json.read_text(encoding="utf-8")


def test_validate_and_inspect_schema_commands(tmp_path):
    runner = CliRunner()
    validate = runner.invoke(
        app,
        ["validate", "--input", str(EXAMPLES / "inventory.csv"), "--kind", "inventory"],
    )
    inspect = runner.invoke(
        app,
        ["inspect-schema", "--input", str(EXAMPLES / "backup_export.csv")],
    )

    assert validate.exit_code == 0, validate.output
    assert "Validated 25 inventory rows" in validate.output
    assert inspect.exit_code == 0, inspect.output
    assert "backup_total_mib" in inspect.output


def test_schema_command_exports_public_contracts():
    result = CliRunner().invoke(app, ["schema", "--kind", "policy"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "PolicyPack" in payload["title"]


def test_schema_command_exports_identity_override_contract():
    result = CliRunner().invoke(app, ["schema", "--kind", "identity-overrides"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "IdentityOverrideSet" in payload["title"]


def test_schema_command_exports_compatibility_matrix():
    result = CliRunner().invoke(app, ["schema", "--kind", "compatibility"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_versions"]["feature"] == FEATURE_SCHEMA_VERSION
    assert payload["default_policy"]["compatible_schema_versions"]["policy"] == POLICY_SCHEMA_VERSION


def test_cli_accepts_local_policy_pack_yaml(tmp_path):
    policy_path = tmp_path / "policy.yml"
    output = tmp_path / "top.csv"
    policy_path.write_text(
        yaml.safe_dump(DEFAULT_POLICY_PACK.model_dump(mode="json")),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--inventory",
            str(EXAMPLES / "inventory.csv"),
            "--backup",
            str(EXAMPLES / "backup_export.csv"),
            "--output",
            str(output),
            "--policy",
            str(policy_path),
            "--top-n",
            "3",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()


def test_policy_impact_reports_candidate_policy_changes(tmp_path):
    output = tmp_path / "top.csv"
    assessment_json = tmp_path / "assessment.json"
    candidate = tmp_path / "candidate-policy.yml"
    analyze_result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--inventory",
            str(EXAMPLES / "inventory.csv"),
            "--backup",
            str(EXAMPLES / "backup_export.csv"),
            "--output",
            str(output),
            "--assessment-json",
            str(assessment_json),
            "--top-n",
            "5",
        ],
    )
    payload = DEFAULT_POLICY_PACK.model_dump(mode="json")
    payload["rules"][0]["score"] = 0
    candidate.write_text(yaml.safe_dump(payload), encoding="utf-8")

    impact_result = CliRunner().invoke(
        app,
        [
            "policy-impact",
            "--assessment-json",
            str(assessment_json),
            "--candidate-policy",
            str(candidate),
        ],
    )

    assert analyze_result.exit_code == 0, analyze_result.output
    assert impact_result.exit_code == 0, impact_result.output
    impact = json.loads(impact_result.output)
    assert impact["workload_count"] == 25
    assert impact["score_changes"] > 0


def test_workflow_pack_writes_handoff_artifacts(tmp_path):
    output = tmp_path / "top.csv"
    assessment_json = tmp_path / "assessment.json"
    workflow_dir = tmp_path / "workflow"
    analyze_result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--inventory",
            str(EXAMPLES / "inventory.csv"),
            "--backup",
            str(EXAMPLES / "backup_export.csv"),
            "--output",
            str(output),
            "--assessment-json",
            str(assessment_json),
            "--top-n",
            "5",
        ],
    )
    workflow_result = CliRunner().invoke(
        app,
        [
            "workflow-pack",
            "--assessment-json",
            str(assessment_json),
            "--output-dir",
            str(workflow_dir),
            "--top-n",
            "5",
        ],
    )

    assert analyze_result.exit_code == 0, analyze_result.output
    assert workflow_result.exit_code == 0, workflow_result.output
    assert (workflow_dir / "executive-summary.md").exists()
    assert (workflow_dir / "discovery-plan.md").exists()
    assert (workflow_dir / "tasks.csv").exists()
    assert (workflow_dir / "business-worklist.csv").exists()
    assert (workflow_dir / "business-impact-summary.json").exists()
    assert (workflow_dir / "data-request-checklist.csv").exists()
    queues = json.loads((workflow_dir / "work-queues.json").read_text(encoding="utf-8"))
    packets = json.loads((workflow_dir / "evidence-packets.json").read_text(encoding="utf-8"))
    comparison = json.loads((workflow_dir / "ranking-mode-comparison.json").read_text(encoding="utf-8"))
    impact = json.loads((workflow_dir / "business-impact-summary.json").read_text(encoding="utf-8"))
    executive = (workflow_dir / "executive-summary.md").read_text(encoding="utf-8")
    checklist = (workflow_dir / "data-request-checklist.csv").read_text(encoding="utf-8")
    assert "MIGRATION_REVIEW" in queues
    assert queues["MIGRATION_REVIEW"][0]["recommended_next_step"]
    assert packets
    assert "balanced" in comparison
    assert impact["presentation_counts"]["strong_candidate"] > 0
    assert "Business Impact" in executive
    assert "migration plan" in executive
    assert "business_question" in checklist


def test_product_surface_commands_use_assessment_artifacts(tmp_path):
    output = tmp_path / "top.csv"
    assessment_json = tmp_path / "assessment.json"
    workflow_dir = tmp_path / "workflow"
    zip_path = tmp_path / "handoff.zip"
    analyze_result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--inventory",
            str(EXAMPLES / "inventory.csv"),
            "--backup",
            str(EXAMPLES / "backup_export.csv"),
            "--output",
            str(output),
            "--assessment-json",
            str(assessment_json),
            "--top-n",
            "5",
        ],
    )
    assessment = json.loads(assessment_json.read_text(encoding="utf-8"))
    workload_key = assessment["workloads"][0]["workload_key"]

    missing_result = CliRunner().invoke(app, ["missing-evidence", "--assessment-json", str(assessment_json)])
    preview_result = CliRunner().invoke(
        app,
        ["preview-top-findings", "--assessment-json", str(assessment_json), "--top-n", "3"],
    )
    explain_result = CliRunner().invoke(
        app,
        [
            "explain-workload",
            "--assessment-json",
            str(assessment_json),
            "--workload-key",
            workload_key,
        ],
    )
    thresholds_result = CliRunner().invoke(app, ["describe-thresholds"])
    workflow_result = CliRunner().invoke(
        app,
        ["workflow-pack", "--assessment-json", str(assessment_json), "--output-dir", str(workflow_dir)],
    )
    handoff_result = CliRunner().invoke(
        app,
        ["handoff-bundle", "--source-dir", str(workflow_dir), "--output", str(zip_path)],
    )

    assert analyze_result.exit_code == 0, analyze_result.output
    assert missing_result.exit_code == 0, missing_result.output
    assert preview_result.exit_code == 0, preview_result.output
    assert explain_result.exit_code == 0, explain_result.output
    assert thresholds_result.exit_code == 0, thresholds_result.output
    assert workflow_result.exit_code == 0, workflow_result.output
    assert handoff_result.exit_code == 0, handoff_result.output
    assert "missing_evidence" in json.loads(missing_result.output)
    assert len(json.loads(preview_result.output)) == 3
    assert json.loads(explain_result.output)["workload_key"] == workload_key
    assert "recent_backup_days" in json.loads(thresholds_result.output)
    assert zip_path.exists()


def test_privacy_scan_detects_needles_and_secret_patterns(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    (output_dir / "summary.txt").write_text("safe\npassword=example\nworkload-name\n", encoding="utf-8")
    report = tmp_path / "privacy-scan.json"

    result = CliRunner().invoke(
        app,
        [
            "privacy-scan",
            "--path",
            str(output_dir),
            "--needle",
            "workload-name",
            "--output-json",
            str(report),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    kinds = {finding["kind"] for finding in payload["findings"]}
    assert kinds >= {"NEEDLE", "SECRET_ASSIGNMENT"}
