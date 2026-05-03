from __future__ import annotations

import csv

from s3_compat_replay.models import Mismatch, OperationFamilyProfile, ProbeResult, ProbeResults, UsageProfile
from s3_compat_replay.report import MISMATCH_COLUMNS, NEEDS_COLUMNS, build_summary, summary_markdown, write_mismatches_csv, write_needs_csv


def _profile():
    return UsageProfile(
        source_bucket="source-bucket-example",
        event_count=1,
        processed_event_count=1,
        operation_families={"object_read": OperationFamilyProfile(count=1, event_names={"GetObject": 1})},
    )


def test_writes_compatibility_needs_csv_with_exact_column_order(tmp_path):
    path = tmp_path / "needs.csv"
    write_needs_csv(path, _profile())
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        assert next(reader) == NEEDS_COLUMNS


def test_writes_mismatches_csv_with_exact_column_order(tmp_path):
    mismatch = Mismatch(
        severity="BLOCKER",
        probe_id="p",
        operation_family="object_read",
        operation="GetObject",
        expected="200",
        actual="403",
        mismatch_code="STATUS_CODE_MISMATCH",
        reason_text="bad status",
        business_impact="impact",
        suggested_human_question="question?",
    )
    results = ProbeResults(
        run_id="run",
        endpoint_url_redacted="https://target.example.invalid",
        target_bucket_redacted="bucket",
        scratch_prefix="compat-replay/",
        started_at="t",
        finished_at="t",
        cleanup={"attempted": False, "succeeded": True, "cleanup_manifest": None},
        results=[ProbeResult(probe_id="p", family="object_read", status="FAIL", mismatches=[mismatch])],
    )
    path = tmp_path / "mismatches.csv"
    write_mismatches_csv(path, results)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        assert next(reader) == MISMATCH_COLUMNS


def test_summary_json_has_compatibility_status():
    mismatch = Mismatch(
        severity="BLOCKER",
        probe_id="p",
        operation_family="object_read",
        operation="GetObject",
        expected="200",
        actual="403",
        mismatch_code="STATUS_CODE_MISMATCH",
        reason_text="bad status",
        business_impact="impact",
        suggested_human_question="question?",
    )
    results = ProbeResults(
        run_id="run",
        endpoint_url_redacted="https://target.example.invalid",
        target_bucket_redacted="bucket",
        scratch_prefix="compat-replay/",
        started_at="t",
        finished_at="t",
        probes_failed=1,
        cleanup={"attempted": False, "succeeded": True, "cleanup_manifest": None},
        results=[ProbeResult(probe_id="p", family="object_read", status="FAIL", mismatches=[mismatch])],
    )
    summary = build_summary(_profile(), results)
    assert summary.compatibility_status == "FAIL"


def test_generated_markdown_summary_includes_top_risks_and_next_questions():
    summary = build_summary(_profile())
    markdown = summary_markdown(summary)
    assert "Top Risks" in markdown
    assert "Recommended Next Questions" in markdown
