from rag_permission_canary.models import RunResults, TestResult as CanaryTestResult
from rag_permission_canary.redact import redact_results, redact_text


def test_redaction_hides_user_doc_titles_metadata_and_canaries():
    results = RunResults(
        run_id="r",
        pack_id="p",
        content_set_id="c",
        endpoint_id="e",
        started_at="s",
        finished_at="f",
        aggregate_status="FAIL",
        test_results=[CanaryTestResult(test_case_id="tc", user_id="user_hr", expected_result="FORBIDDEN", status="FAIL", target_doc_id="doc_fin", reason_codes=["FORBIDDEN_CANARY_LEAKED"], answer_excerpt_redacted="CANARY_FINANCE_BRAVO Finance Draft finance")],
    )
    redacted = redact_results(results)
    assert redacted.test_results[0].user_id == "user_001"
    assert redacted.test_results[0].target_doc_id == "doc_001"
    assert "CANARY_FINANCE_BRAVO" not in redacted.test_results[0].answer_excerpt_redacted


def test_redaction_preserves_status_and_reason_codes():
    results = RunResults(run_id="r", pack_id="p", content_set_id="c", endpoint_id="e", started_at="s", finished_at="f", aggregate_status="FAIL", test_results=[CanaryTestResult(test_case_id="tc", user_id="u", expected_result="FORBIDDEN", status="FAIL", reason_codes=["FORBIDDEN_CANARY_LEAKED"])])
    redacted = redact_results(results)
    assert redacted.test_results[0].status == "FAIL"
    assert redacted.test_results[0].reason_codes == ["FORBIDDEN_CANARY_LEAKED"]
