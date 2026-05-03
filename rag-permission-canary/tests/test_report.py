from rag_permission_canary.models import RunResults, TestResult as CanaryTestResult
from rag_permission_canary.report import write_markdown_report


def test_report_includes_caveats_and_reason_codes(tmp_path):
    results = RunResults(run_id="r", pack_id="p", content_set_id="c", endpoint_id="e", started_at="s", finished_at="f", aggregate_status="REVIEW", summary={"test_count": 1}, leakage_summary={"forbidden_canary_leaks": 0}, test_results=[CanaryTestResult(test_case_id="tc", user_id="u", expected_result="ALLOWED", status="REVIEW", reason_codes=["ALLOWED_EVIDENCE_MISSING"])])
    output = tmp_path / "report.md"
    write_markdown_report(output, results)
    text = output.read_text(encoding="utf-8")
    assert "Data Honesty Caveats" in text
    assert "ALLOWED_EVIDENCE_MISSING" in text
