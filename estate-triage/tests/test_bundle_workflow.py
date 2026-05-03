import csv
import json
import shutil
from collections import Counter
from pathlib import Path

import yaml
from typer.testing import CliRunner

from estate_triage.api import analyze_csv_estate
from estate_triage.assessment import RankingMode
from estate_triage.bundle import (
    FeedbackFile,
    FeedbackItem,
    analyze_bundle,
    summarize_feedback,
    summarize_feedback_ledger,
)
from estate_triage.cli import app
from estate_triage.real_world_generator import generate_real_world_bundle
from estate_triage.policy import DEFAULT_POLICY_PACK


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
RUNNER = CliRunner()


def copy_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "estate-bundle"
    shutil.copytree(EXAMPLES / "estate-bundle", bundle)
    return bundle


def test_utilization_evidence_feeds_rightsizing_motion_assessment():
    assessment = analyze_csv_estate(
        inventory_path=EXAMPLES / "inventory.csv",
        backup_path=EXAMPLES / "backup_export.csv",
        utilization_path=EXAMPLES / "utilization.csv",
    )
    workload = next(item for item in assessment.workloads if item.identity.inventory.uuid == "inv-uuid-007")
    rightsizing = next(
        motion
        for motion in workload.policy_evaluation.motion_assessments
        if motion.motion == "RIGHTSIZING_REVIEW"
    )

    assert workload.feature_set.value("cpu_p95_pct") == 3
    assert workload.feature_set.value("memory_p95_pct") == 22
    assert "IDLE_CPU" in rightsizing.reason_codes
    assert "OVERSIZED_MEMORY" in rightsizing.reason_codes
    assert rightsizing.allocation_only_rightsizing is False


def test_init_mapping_and_validate_utilization_json(tmp_path):
    mapping = tmp_path / "utilization-map.yml"
    validation = tmp_path / "validation.json"

    init_result = RUNNER.invoke(
        app,
        [
            "init-mapping",
            "--kind",
            "utilization",
            "--input",
            str(EXAMPLES / "utilization.csv"),
            "--output",
            str(mapping),
        ],
    )
    validate_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(EXAMPLES / "utilization.csv"),
            "--kind",
            "utilization",
            "--mapping",
            str(mapping),
            "--output-json",
            str(validation),
        ],
    )

    assert init_result.exit_code == 0, init_result.output
    assert validate_result.exit_code == 0, validate_result.output
    payload = json.loads(validation.read_text(encoding="utf-8"))
    assert payload["input_kind"] == "utilization"
    assert payload["recognized_records"] == 5
    assert payload["missing_recommended_fields"] == []
    assert payload["readiness_grade"] == "A"
    assert payload["readiness_score"] == 100
    assert payload["data_request_checklist"] == []
    assert payload["matchability_forecast"]["forecast"] == "high"
    assert any(profile["field"] == "cpu_p95_pct" for profile in payload["field_profiles"])


def test_analyze_bundle_writes_redacted_outputs_and_fingerprints(tmp_path):
    bundle = copy_bundle(tmp_path)
    result = RUNNER.invoke(app, ["analyze-bundle", str(bundle), "--top-n", "5"])

    assert result.exit_code == 0, result.output
    output_dir = bundle / "outputs"
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assessment_text = (output_dir / "assessment.json").read_text(encoding="utf-8")
    validation_text = (output_dir / "validation.json").read_text(encoding="utf-8")
    fingerprints = json.loads((output_dir / "input-fingerprints.json").read_text(encoding="utf-8"))

    assert summary["input"]["utilization_rows"] == 5
    assert summary["feedback"]["items"] == 1
    assert summary["readiness"]["grade"] in {"A", "B", "C", "D", "F"}
    assert "remediation_actions" in summary["readiness"]
    assert "mig-payments-api" not in assessment_text
    assert "inv-uuid-001" not in assessment_text
    assert "job-a" not in assessment_text
    assert "repo-a" not in assessment_text
    assert "inputs/inventory.csv" not in assessment_text
    assert "inputs/inventory.csv" not in validation_text
    assert len(fingerprints["inputs"]) == 3


def test_fingerprint_feedback_corpus_and_policy_commands(tmp_path):
    bundle = copy_bundle(tmp_path)
    corpus = tmp_path / "corpus" / "case1"
    policy = tmp_path / "policy.yml"
    policy.write_text(
        yaml.safe_dump(DEFAULT_POLICY_PACK.model_dump(mode="json")),
        encoding="utf-8",
    )
    fingerprints = tmp_path / "fingerprints.json"
    feedback = tmp_path / "feedback.yml"

    fp_result = RUNNER.invoke(
        app,
        [
            "fingerprint",
            str(EXAMPLES / "inventory.csv"),
            str(EXAMPLES / "backup_export.csv"),
            "--output",
            str(fingerprints),
        ],
    )
    feedback_result = RUNNER.invoke(
        app,
        ["feedback-template", "--output", str(feedback), "--assessment-id", "demo"],
    )
    corpus_result = RUNNER.invoke(
        app,
        ["sanitize-corpus", "--bundle", str(bundle), "--output", str(corpus)],
    )
    validate_corpus_result = RUNNER.invoke(
        app,
        ["validate-corpus", "--corpus", str(corpus.parent)],
    )
    policy_result = RUNNER.invoke(
        app,
        ["test-policy", "--policy", str(policy), "--corpus", str(corpus.parent)],
    )

    assert fp_result.exit_code == 0, fp_result.output
    assert feedback_result.exit_code == 0, feedback_result.output
    assert corpus_result.exit_code == 0, corpus_result.output
    assert validate_corpus_result.exit_code == 0, validate_corpus_result.output
    assert policy_result.exit_code == 0, policy_result.output
    assert (corpus / "case.yml").exists()
    case_payload = yaml.safe_load((corpus / "case.yml").read_text(encoding="utf-8"))
    policy_payload = json.loads(policy_result.output)
    assert case_payload["expected_outcomes"]["workload_count"] > 0
    assert policy_payload["cases"] == 1
    assert policy_payload["status"] == "passed"
    assert json.loads(validate_corpus_result.output)["status"] == "passed"


def test_validate_corpus_fails_on_incomplete_case(tmp_path):
    corpus = tmp_path / "corpus" / "case1"
    corpus.mkdir(parents=True)
    (corpus / "case.yml").write_text(
        yaml.safe_dump(
            {
                "source_bundle": "missing",
                "expected_summary": {},
            }
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["validate-corpus", "--corpus", str(corpus.parent)])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "failed"
    assert payload["errors"] >= 1


def test_feedback_summary_supports_business_outcome_labels():
    summary = summarize_feedback(
        FeedbackFile(
            assessment_id="feedback-test",
            manual_triage_minutes=120,
            tool_triage_minutes=45,
            feedback=[
                FeedbackItem(
                    workload_key="a",
                    finding="MIGRATION_REVIEW",
                    outcome="accepted",
                    converted=True,
                    next_step="technical_workshop",
                ),
                FeedbackItem(workload_key="b", finding="DR_TIER_REVIEW", outcome="rejected"),
                FeedbackItem(workload_key="c", finding="RIGHTSIZING_REVIEW", outcome="needs_more_data"),
                FeedbackItem(workload_key="d", finding="ARCHIVE_REVIEW", outcome="wrong_motion"),
                FeedbackItem(workload_key="e", finding="DR_TIER_REVIEW", outcome="false_positive"),
                FeedbackItem(workload_key="external", finding="ARCHIVE_REVIEW", outcome="missed_opportunity"),
            ],
        )
    )

    assert summary["items"] == 6
    assert summary["reviewed_items"] == 5
    assert summary["outcomes"]["accepted"] == 1
    assert summary["outcomes"]["rejected"] == 1
    assert summary["outcomes"]["needs_more_data"] == 1
    assert summary["outcomes"]["wrong_motion"] == 1
    assert summary["outcomes"]["missed_opportunity"] == 1
    assert summary["rates"]["false_positive_rate"] == 0.2
    assert summary["rates"]["false_negative_count"] == 1
    assert summary["rates"]["conversion_rate"] == 0.2
    assert summary["time_benchmark"]["time_saved_minutes"] == 75
    assert summary["time_benchmark"]["time_saved_pct"] == 62.5


def test_feedback_summary_cli_reports_business_metrics(tmp_path):
    feedback = tmp_path / "feedback.yml"
    feedback.write_text(
        yaml.safe_dump(
            {
                "assessment_id": "metrics-test",
                "manual_triage_minutes": 90,
                "tool_triage_minutes": 30,
                "feedback": [
                    {
                        "workload_key": "a",
                        "finding": "MIGRATION_REVIEW",
                        "outcome": "accepted",
                        "converted": True,
                        "next_step": "discovery_call",
                    },
                    {
                        "workload_key": "b",
                        "finding": "DR_TIER_REVIEW",
                        "outcome": "false_positive",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["feedback-summary", "--feedback", str(feedback)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["rates"]["false_positive_rate"] == 0.5
    assert payload["rates"]["conversion_rate"] == 0.5
    assert payload["time_benchmark"]["time_saved_minutes"] == 60


def test_outcome_ledger_aggregates_feedback_files(tmp_path):
    first = tmp_path / "first.yml"
    second = tmp_path / "second.yml"
    first.write_text(
        yaml.safe_dump(
            {
                "assessment_id": "first",
                "manual_triage_minutes": 60,
                "tool_triage_minutes": 20,
                "feedback": [
                    {"workload_key": "a", "finding": "MIGRATION_REVIEW", "outcome": "accepted", "converted": True}
                ],
            }
        ),
        encoding="utf-8",
    )
    second.write_text(
        yaml.safe_dump(
            {
                "assessment_id": "second",
                "manual_triage_minutes": 90,
                "tool_triage_minutes": 30,
                "feedback": [
                    {"workload_key": "b", "finding": "DR_TIER_REVIEW", "outcome": "false_positive"},
                    {"workload_key": "external", "finding": "ARCHIVE_REVIEW", "outcome": "missed_opportunity"},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = RUNNER.invoke(app, ["outcome-ledger", str(first), str(second)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["assessments"] == 2
    assert payload["rates"]["false_positive_rate"] == 0.5
    assert payload["rates"]["false_negative_count"] == 1
    assert payload["conversion"]["converted"] == 1
    assert payload["time_benchmark"]["time_saved_minutes"] == 100


def test_feedback_ledger_helper_aggregates_rates():
    payload = summarize_feedback_ledger(
        [
            FeedbackFile(
                assessment_id="a",
                feedback=[
                    FeedbackItem(workload_key="a", finding="MIGRATION_REVIEW", outcome="accepted", converted=True)
                ],
            ),
            FeedbackFile(
                assessment_id="b",
                feedback=[
                    FeedbackItem(workload_key="b", finding="DR_TIER_REVIEW", outcome="false_positive")
                ],
            ),
        ]
    )

    assert payload["assessments"] == 2
    assert payload["rates"]["accepted_rate"] == 0.5
    assert payload["rates"]["false_positive_rate"] == 0.5


def test_policy_corpus_command_fails_on_expected_outcome_regression(tmp_path):
    bundle = copy_bundle(tmp_path)
    corpus = tmp_path / "corpus" / "case1"
    policy = tmp_path / "policy.yml"
    payload = DEFAULT_POLICY_PACK.model_dump(mode="json")
    payload["rules"][0]["score"] = 1
    policy.write_text(yaml.safe_dump(payload), encoding="utf-8")

    corpus_result = RUNNER.invoke(
        app,
        ["sanitize-corpus", "--bundle", str(bundle), "--output", str(corpus)],
    )
    policy_result = RUNNER.invoke(
        app,
        ["test-policy", "--policy", str(policy), "--corpus", str(corpus.parent)],
    )

    assert corpus_result.exit_code == 0, corpus_result.output
    assert policy_result.exit_code == 1
    result_payload = json.loads(policy_result.output)
    assert result_payload["status"] == "failed"
    assert result_payload["failures"] > 0


def test_real_world_generator_covers_business_motions_and_data_quality(tmp_path):
    bundle = tmp_path / "generated-bundle"
    generated = generate_real_world_bundle(bundle)
    result = analyze_bundle(bundle, top_n=10, ranking_mode=RankingMode.PER_MOTION)
    motions = result.summary["motions"]
    quality_codes = {
        finding.code
        for finding in result.assessment.data_quality
    } | {
        finding.code
        for workload in result.assessment.workloads
        for finding in workload.data_quality
    }
    with (bundle / "outputs" / "top.csv").open("r", encoding="utf-8", newline="") as handle:
        ranked_motions = Counter(row["primary_motion"] for row in csv.DictReader(handle))

    assert generated.inventory_rows >= 90
    assert generated.backup_rows >= 90
    assert generated.utilization_rows >= 30
    assert motions["MIGRATION_REVIEW"] > 0
    assert motions["ARCHIVE_REVIEW"] > 0
    assert motions["RIGHTSIZING_REVIEW"] > 0
    assert motions["DR_TIER_REVIEW"] > 0
    assert "UUID_NAME_CONFLICT" in quality_codes
    assert "DUPLICATE_NAME_CANDIDATES" in quality_codes
    assert "UNMATCHED_INVENTORY" in quality_codes
    assert "PARSE_WARNING" in quality_codes
    assert "IN_USE_EXCEEDS_PROVISIONED" in quality_codes
    assert generated.scenario_counts["contradictory_records"] > 0
    assert generated.scenario_counts["sparse_minimal"] > 0
    assert generated.scenario_counts["rich_context"] > 0
    assert generated.scenario_counts["extreme_outlier"] > 0
    assert ranked_motions == {
        "MIGRATION_REVIEW": 10,
        "ARCHIVE_REVIEW": 10,
        "RIGHTSIZING_REVIEW": 10,
        "DR_TIER_REVIEW": 10,
    }


def test_generate_real_world_data_cli(tmp_path):
    output = tmp_path / "generated"
    result = RUNNER.invoke(
        app,
        ["generate-real-world-data", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["inventory_rows"] >= 90
    assert (output / "coverage.json").exists()
    assert (output / "generator-profile.yml").exists()
    assert payload["profile_name"] == "coverage"


def test_real_world_generator_supports_multi_source_bundle(tmp_path):
    output = tmp_path / "multi-source"
    result = RUNNER.invoke(
        app,
        ["generate-real-world-data", "--output", str(output), "--multi-source"],
    )
    analyze_result = RUNNER.invoke(
        app,
        ["analyze-bundle", str(output), "--top-n", "10", "--ranking-mode", "per_motion"],
    )

    assert result.exit_code == 0, result.output
    assert analyze_result.exit_code == 0, analyze_result.output
    payload = json.loads(result.output)
    summary = json.loads((output / "outputs" / "summary.json").read_text(encoding="utf-8"))
    source_metadata = yaml.safe_load((output / "source-metadata.yml").read_text(encoding="utf-8"))
    assert payload["multi_source"] is True
    assert "inputs/inventory_secondary.csv" in payload["input_files"]
    assert "inputs/backup_secondary.csv" in payload["input_files"]
    assert summary["input"]["inventory_rows"] == payload["inventory_rows"]
    assert summary["input"]["backup_rows"] == payload["backup_rows"]
    assert source_metadata["multi_source"] is True
    assert "inputs/inventory_secondary.csv" in source_metadata["source_windows"]
    source_window_codes = {
        finding["code"]
        for finding in summary["readiness"]["source_window_findings"]
    }
    assert source_window_codes >= {"STALE_SOURCE_WINDOW", "SOURCE_WINDOW_SKEW"}


def test_real_world_generator_edge_cases_exercise_csv_readiness(tmp_path):
    output = tmp_path / "edge-cases"
    result = RUNNER.invoke(
        app,
        ["generate-real-world-data", "--output", str(output), "--edge-cases"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    edge_files = set(payload["edge_case_files"])
    assert "edge-cases/duplicate_headers_inventory.csv" in edge_files
    assert "edge-cases/malformed_inventory.csv" in edge_files
    assert "edge-cases/non_utf8_inventory.csv" in edge_files
    assert (output / "edge-cases" / "edge-case-manifest.yml").exists()


def test_edge_case_validation_detects_duplicate_and_irregular_rows(tmp_path):
    output = tmp_path / "edge-cases"
    generate_real_world_bundle(output, edge_cases=True)

    duplicate_report = tmp_path / "duplicate-report.json"
    duplicate_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "duplicate_headers_inventory.csv"),
            "--kind",
            "inventory",
            "--output-json",
            str(duplicate_report),
        ],
    )
    extra_report = tmp_path / "extra-report.json"
    extra_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "extra_columns_inventory.csv"),
            "--kind",
            "inventory",
            "--output-json",
            str(extra_report),
        ],
    )
    missing_report = tmp_path / "missing-report.json"
    missing_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "missing_columns_inventory.csv"),
            "--kind",
            "inventory",
            "--output-json",
            str(missing_report),
        ],
    )

    assert duplicate_result.exit_code == 0, duplicate_result.output
    assert extra_result.exit_code == 0, extra_result.output
    assert missing_result.exit_code == 0, missing_result.output
    duplicate_payload = json.loads(duplicate_report.read_text(encoding="utf-8"))
    extra_payload = json.loads(extra_report.read_text(encoding="utf-8"))
    missing_payload = json.loads(missing_report.read_text(encoding="utf-8"))
    assert {finding["code"] for finding in duplicate_payload["data_quality"]} >= {"DUPLICATE_HEADER"}
    assert {finding["code"] for finding in extra_payload["data_quality"]} >= {"EXTRA_CSV_COLUMNS"}
    assert {finding["code"] for finding in missing_payload["data_quality"]} >= {"MISSING_CSV_COLUMNS"}


def test_edge_case_validation_accepts_embedded_units_and_localized_inputs(tmp_path):
    output = tmp_path / "edge-cases"
    generate_real_world_bundle(output, edge_cases=True)

    embedded_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "embedded_delimiters_inventory.csv"),
            "--kind",
            "inventory",
        ],
    )
    mixed_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "mixed_units_inventory.csv"),
            "--kind",
            "inventory",
        ],
    )
    localized_inventory_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "localized_inventory.csv"),
            "--kind",
            "inventory",
        ],
    )
    localized_backup_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "localized_backup_export.csv"),
            "--kind",
            "backup",
        ],
    )

    assert embedded_result.exit_code == 0, embedded_result.output
    assert mixed_result.exit_code == 0, mixed_result.output
    assert localized_inventory_result.exit_code == 0, localized_inventory_result.output
    assert localized_backup_result.exit_code == 0, localized_backup_result.output
    assert "Validated 1 inventory rows" in embedded_result.output
    assert "Validated 1 backup rows" in localized_backup_result.output


def test_edge_case_validation_rejects_malformed_and_non_utf8_csv(tmp_path):
    output = tmp_path / "edge-cases"
    generate_real_world_bundle(output, edge_cases=True)

    malformed_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "malformed_inventory.csv"),
            "--kind",
            "inventory",
        ],
    )
    non_utf8_result = RUNNER.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "edge-cases" / "non_utf8_inventory.csv"),
            "--kind",
            "inventory",
        ],
    )

    assert malformed_result.exit_code == 1
    assert "Could not parse CSV file" in malformed_result.output
    assert non_utf8_result.exit_code == 1
    assert "not valid UTF-8" in non_utf8_result.output


def test_real_world_generator_supports_custom_calibration_profile(tmp_path):
    profile = tmp_path / "profile.yml"
    profile.write_text(
        yaml.safe_dump(
            {
                "name": "field-calibration-example",
                "source": "sanitized-field-derived",
                "description": "Test profile proving generator counts can come from explicit calibration.",
                "scenario_counts": {
                    "migration_easy": 2,
                    "dr_large_low_change": 1,
                    "archive_powered_off_stale": 1,
                    "rightsizing_util_backed": 1,
                    "allocation_only_rightsizing": 1,
                    "snapshot_blocker": 1,
                    "no_backup_match": 1,
                    "name_only_match": 1,
                    "missing_storage_used": 1,
                    "uuid_name_conflict": 1,
                    "duplicate_name_candidates": 1,
                    "ambiguous_backup_date": 1,
                },
                "backup_only_unmatched_rows": 3,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "custom-generated"
    result = RUNNER.invoke(
        app,
        [
            "generate-real-world-data",
            "--output",
            str(output),
            "--profile-config",
            str(profile),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["profile_name"] == "field-calibration-example"
    assert payload["profile_source"] == "sanitized-field-derived"
    assert payload["inventory_rows"] == 13
    assert payload["backup_only_unmatched_rows"] == 3
    assert payload["scenario_counts"]["migration_easy"] == 2
    assert yaml.safe_load((output / "generator-profile.yml").read_text(encoding="utf-8"))[
        "source"
    ] == "sanitized-field-derived"


def test_validate_generator_profile_requires_field_derived_source(tmp_path):
    profile = tmp_path / "profile.yml"
    profile.write_text(
        yaml.safe_dump(
            {
                "name": "synthetic-test-profile",
                "source": "synthetic-profile",
                "description": "Synthetic profile should fail field-derived enforcement.",
                "scenario_counts": {"migration_easy": 1},
                "backup_only_unmatched_rows": 0,
            }
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        [
            "validate-generator-profile",
            "--profile-config",
            str(profile),
            "--require-field-derived",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["field_derived"] is False
    assert payload["errors"]


def test_validate_generator_profile_accepts_field_derived_source_and_schema(tmp_path):
    schema_result = RUNNER.invoke(app, ["schema", "--kind", "generator-profile"])
    profile = tmp_path / "profile.yml"
    profile.write_text(
        yaml.safe_dump(
            {
                "name": "sanitized-field-profile",
                "source": "sanitized-field-derived",
                "description": "Profile derived from sanitized field observations.",
                "calibration_evidence": {
                    "assessment_count": 1,
                    "inventory_rows_observed": 50,
                    "backup_rows_observed": 45,
                    "utilization_rows_observed": 20,
                    "sanitization_method": "local redaction and aggregated scenario counts",
                    "source_window": "2026-Q1",
                },
                "scenario_counts": {
                    "migration_easy": 2,
                    "rightsizing_util_backed": 1,
                },
                "backup_only_unmatched_rows": 1,
            }
        ),
        encoding="utf-8",
    )
    result = RUNNER.invoke(
        app,
        [
            "validate-generator-profile",
            "--profile-config",
            str(profile),
            "--require-field-derived",
        ],
    )

    assert schema_result.exit_code == 0, schema_result.output
    assert "scenario_counts" in schema_result.output
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["source_declares_field_derived"] is True
    assert payload["calibration_evidence_present"] is True
    assert payload["field_derived"] is True
    assert payload["inventory_rows_expected"] == 3
    assert payload["backup_rows_expected"] == 4
    assert payload["utilization_rows_expected"] == 3
    assert payload["scenario_frequencies"]["migration_easy"] == 0.666667
    assert "migration_easy" in payload["scenario_confidence_intervals_95"]
    assert "migration_easy|dr_large_low_change" in payload["scenario_correlations"]


def test_derive_generator_profile_from_sanitized_bundle_assessment(tmp_path):
    bundle = copy_bundle(tmp_path)
    profile = tmp_path / "derived-profile.yml"

    analyze_result = RUNNER.invoke(app, ["analyze-bundle", str(bundle), "--top-n", "5"])
    derive_result = RUNNER.invoke(
        app,
        [
            "derive-generator-profile",
            "--bundle",
            str(bundle),
            "--output",
            str(profile),
            "--name",
            "sanitized-field-derived-test",
            "--source",
            "sanitized-field-derived",
            "--sanitization-method",
            "strict redacted assessment artifact",
            "--source-window",
            "test-window",
        ],
    )
    validate_result = RUNNER.invoke(
        app,
        [
            "validate-generator-profile",
            "--profile-config",
            str(profile),
            "--require-field-derived",
        ],
    )

    assert analyze_result.exit_code == 0, analyze_result.output
    assert derive_result.exit_code == 0, derive_result.output
    assert validate_result.exit_code == 0, validate_result.output
    payload = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert payload["calibration_evidence"]["sanitization_method"] == "strict redacted assessment artifact"
    assert sum(payload["scenario_counts"].values()) > 0


def test_compare_assessments_reports_repeated_run_deltas(tmp_path):
    bundle = copy_bundle(tmp_path)
    first = bundle / "outputs" / "assessment-first.json"
    second = bundle / "outputs" / "assessment-second.json"

    analyze_result = RUNNER.invoke(app, ["analyze-bundle", str(bundle), "--top-n", "5"])
    shutil.copyfile(bundle / "outputs" / "assessment.json", first)
    second.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    compare_result = RUNNER.invoke(
        app,
        [
            "compare-assessments",
            "--baseline",
            str(first),
            "--current",
            str(second),
        ],
    )

    assert analyze_result.exit_code == 0, analyze_result.output
    assert compare_result.exit_code == 0, compare_result.output
    payload = json.loads(compare_result.output)
    assert payload["workload_delta"] == 0
    assert payload["added_workload_keys"] == []
    assert payload["removed_workload_keys"] == []
