from __future__ import annotations

import json

import yaml
from typer.testing import CliRunner

from s3_compat_replay.cli import app
from s3_compat_replay.cloudtrail_parse import parse_cloudtrail
from s3_compat_replay.real_world import generate_real_world_fixture


def test_real_world_generator_splits_formats_and_covers_inputs(tmp_path):
    fixture = generate_real_world_fixture(tmp_path / "input", event_count=90)
    events, warnings = parse_cloudtrail(tmp_path / "input" / "cloudtrail")
    assert warnings == []
    assert fixture.event_count == 90
    assert len(events) == 90
    assert {event.eventName for event in events} >= {"PutObject", "GetObject", "CreateMultipartUpload", "PutObjectRetention", "GetBucketCors"}
    assert (tmp_path / "input" / "request-hints.yml").exists()
    assert (tmp_path / "input" / "source-bucket-config.yml").exists()
    assert (tmp_path / "input" / "sanitized-http-trace.jsonl").exists()
    assert (tmp_path / "input" / "server-access-log.jsonl").exists()
    assert (tmp_path / "input" / "policy-context.yml").exists()
    assert (tmp_path / "input" / "corpus-calibration.yml").exists()


def test_real_world_cli_end_to_end_assessment(tmp_path):
    runner = CliRunner()
    input_dir = tmp_path / "input"
    run_dir = tmp_path / "run"
    result = runner.invoke(app, ["real-world", "generate", "--output-dir", str(input_dir), "--event-count", "90"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        [
            "analyze",
            "--cloudtrail",
            str(input_dir / "cloudtrail"),
            "--source-bucket",
            "source-bucket-example",
            "--request-hints",
            str(input_dir / "request-hints.yml"),
            "--bucket-config",
            str(input_dir / "source-bucket-config.yml"),
            "--output-profile",
            str(run_dir / "usage-profile.json"),
            "--output-plan",
            str(run_dir / "probe-plan.yml"),
            "--output-needs",
            str(run_dir / "compatibility-needs.csv"),
            "--redact",
        ],
    )
    assert result.exit_code == 0, result.output
    plan_data = yaml.safe_load((run_dir / "probe-plan.yml").read_text(encoding="utf-8"))
    plan_families = {probe["family"] for probe in plan_data["probes"]}
    assert {
        "conditional_requests",
        "range_gets",
        "metadata",
        "encryption_headers",
        "presigned_expiry",
        "list_pagination",
        "versioning_delete_marker",
        "consistency",
        "authz_context",
        "ownership_controls",
        "requester_pays",
    } <= plan_families
    result = runner.invoke(
        app,
        [
            "real-world",
            "simulate-results",
            "--plan",
            str(run_dir / "probe-plan.yml"),
            "--output-results",
            str(run_dir / "probe-results.json"),
            "--output-mismatches",
            str(run_dir / "mismatches.csv"),
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        [
            "summarize",
            "--profile",
            str(run_dir / "usage-profile.json"),
            "--results",
            str(run_dir / "probe-results.json"),
            "--output-summary",
            str(run_dir / "compat-summary.json"),
            "--output-markdown",
            str(run_dir / "compat-summary.md"),
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        [
            "questionnaire",
            "generate",
            "--profile",
            str(run_dir / "usage-profile.json"),
            "--mismatches",
            str(run_dir / "mismatches.csv"),
            "--output",
            str(run_dir / "app-owner-questions.yml"),
            "--output-markdown",
            str(run_dir / "app-owner-questions.md"),
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        [
            "compare-results",
            "--profile",
            str(run_dir / "usage-profile.json"),
            "--results",
            str(run_dir / "probe-results.json"),
            "--output-matrix",
            str(run_dir / "compat-matrix.json"),
            "--output-markdown",
            str(run_dir / "compat-matrix.md"),
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        [
            "real-world",
            "assess",
            "--cloudtrail",
            str(input_dir / "cloudtrail"),
            "--request-hints",
            str(input_dir / "request-hints.yml"),
            "--bucket-config",
            str(input_dir / "source-bucket-config.yml"),
            "--http-trace",
            str(input_dir / "sanitized-http-trace.jsonl"),
            "--server-access-log",
            str(input_dir / "server-access-log.jsonl"),
            "--policy-context",
            str(input_dir / "policy-context.yml"),
            "--business-context",
            str(input_dir / "business-context.yml"),
            "--corpus-calibration",
            str(input_dir / "corpus-calibration.yml"),
            "--profile",
            str(run_dir / "usage-profile.json"),
            "--plan",
            str(run_dir / "probe-plan.yml"),
            "--results",
            str(run_dir / "probe-results.json"),
            "--summary",
            str(run_dir / "compat-summary.json"),
            "--matrix",
            str(run_dir / "compat-matrix.json"),
            "--questionnaire",
            str(run_dir / "app-owner-questions.yml"),
            "--output-json",
            str(run_dir / "assessment.json"),
            "--output-markdown",
            str(run_dir / "assessment.md"),
        ],
    )
    assert result.exit_code == 0, result.output
    assessment = json.loads((run_dir / "assessment.json").read_text(encoding="utf-8"))
    assert assessment["status"] == "PASS"
    assert assessment["input_coverage"]["family_coverage_percent"] == 100.0
    assert assessment["output_coverage"]["plan_family_coverage_percent"] == 100.0
    assert len(assessment["business_impact_findings"]) >= 5
    assert assessment["input_gaps"] == []
    assert assessment["output_gaps"] == []

    closed_input_checks = {
        "has_source_http_transcript",
        "has_body_classes",
        "has_iam_or_bucket_policy_context",
        "has_server_access_log_correlation",
        "has_user_identity_context",
        "has_exact_header_coverage",
        "has_latency_or_retry_distribution",
        "has_real_customer_distribution_support",
        "has_pagination_token_distribution",
        "has_unusual_key_character_set",
        "has_presigned_expiration_distribution",
        "has_event_notification_context",
        "has_replication_context",
        "has_requester_pays_traffic",
        "has_large_multipart_distribution",
        "has_bucket_policy_or_ownership_edge_cases",
    }
    missing_input_checks = [key for key in sorted(closed_input_checks) if not assessment["input_coverage"].get(key)]
    assert missing_input_checks == []
    assert assessment["input_coverage"]["error_shape_count"] >= 4
    assert "encryption_headers" in assessment["input_coverage"]["feature_evidence"]

    closed_output_checks = {
        "has_results_provenance",
        "has_conditional_request_probes",
        "has_range_get_probes",
        "has_encryption_header_probes",
        "has_metadata_header_roundtrip_probes",
        "has_presigned_expiry_boundary_probes",
        "has_cors_multi_origin_matrix",
        "has_list_pagination_probes",
        "has_delete_marker_deep_probes",
        "has_lifecycle_validation_plan",
        "has_consistency_model_probes",
        "has_policy_authz_differentiation",
        "has_ownership_controls_probes",
        "has_requester_pays_probes",
        "has_timing_distribution",
        "has_multi_region_or_addressing_matrix",
        "has_application_confirmation_required_fields",
    }
    missing_output_checks = [key for key in sorted(closed_output_checks) if not assessment["output_coverage"].get(key)]
    assert missing_output_checks == []
    assert assessment["output_coverage"]["has_generic_business_impact"] is False

    probe_results = json.loads((run_dir / "probe-results.json").read_text(encoding="utf-8"))
    generic_impacts = [
        mismatch["mismatch_code"]
        for result in probe_results["results"]
        for mismatch in result.get("mismatches", [])
        if "Observed object-storage behavior may differ" in mismatch.get("business_impact", "")
    ]
    assert generic_impacts == []
