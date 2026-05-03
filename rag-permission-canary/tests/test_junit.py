from pathlib import Path

from rag_permission_canary.junit import write_junit
from rag_permission_canary.models import RunResults, TestResult as CanaryTestResult


def test_junit_maps_fail_to_failure(tmp_path):
    results = RunResults(run_id="r", pack_id="p", content_set_id="c", endpoint_id="e", started_at="s", finished_at="f", aggregate_status="FAIL", test_results=[CanaryTestResult(test_case_id="tc", user_id="u", expected_result="FORBIDDEN", status="FAIL", reason_codes=["PERMISSION_REGRESSION_FAIL"])])
    output = tmp_path / "junit.xml"
    write_junit(output, results)
    assert "<failure" in output.read_text(encoding="utf-8")


def test_junit_maps_review_to_skipped_unless_fail_on_review(tmp_path):
    results = RunResults(run_id="r", pack_id="p", content_set_id="c", endpoint_id="e", started_at="s", finished_at="f", aggregate_status="REVIEW", test_results=[CanaryTestResult(test_case_id="tc", user_id="u", expected_result="ALLOWED", status="REVIEW", reason_codes=["HUMAN_REVIEW_REQUIRED"])])
    skipped = tmp_path / "skipped.xml"
    failed = tmp_path / "failed.xml"
    write_junit(skipped, results)
    write_junit(failed, results, fail_on_review=True)
    assert "<skipped" in skipped.read_text(encoding="utf-8")
    assert "<failure" in failed.read_text(encoding="utf-8")
