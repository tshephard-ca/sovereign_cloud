from rag_permission_canary.leakage_detect import detect_leakage
from rag_permission_canary.models import CanaryTestCase, ExtractedResponse, LeakageCheck


def case() -> CanaryTestCase:
    return CanaryTestCase(
        test_case_id="tc",
        user_id="u",
        query="What does the finance document say?",
        expected_result="FORBIDDEN",
        target_doc_id="doc_fin",
        forbidden_doc_ids=["doc_fin"],
        leakage_checks=LeakageCheck(
            forbidden_canary_texts=["CANARY_FIN"],
            forbidden_doc_titles=["Finance Draft"],
            forbidden_metadata_values=["finance"],
        ),
    )


def test_finds_forbidden_canary_in_answer():
    findings, reasons, _ = detect_leakage(case(), ExtractedResponse(answer_text="CANARY_FIN"), {})
    assert findings
    assert "FORBIDDEN_CANARY_LEAKED" in reasons


def test_finds_forbidden_canary_in_citation_snippet():
    findings, reasons, _ = detect_leakage(case(), ExtractedResponse(citation_snippets=["CANARY_FIN"]), {})
    assert any(f.leakage_type == "FORBIDDEN_CANARY_IN_SNIPPET" for f in findings)


def test_finds_forbidden_doc_id_in_citation():
    findings, reasons, _ = detect_leakage(case(), ExtractedResponse(citation_doc_ids=["doc_fin"]), {})
    assert "FORBIDDEN_DOC_ID_CITED" in reasons


def test_finds_forbidden_title_in_answer():
    findings, reasons, _ = detect_leakage(case(), ExtractedResponse(answer_text="Finance Draft"), {})
    assert "FORBIDDEN_TITLE_LEAKED" in reasons


def test_finds_forbidden_metadata_value():
    findings, reasons, _ = detect_leakage(case(), ExtractedResponse(metadata_values=["finance"]), {})
    assert "FORBIDDEN_METADATA_LEAKED" in reasons


def test_finds_forbidden_raw_context():
    findings, reasons, _ = detect_leakage(case(), ExtractedResponse(raw_context="CANARY_FIN"), {})
    assert "FORBIDDEN_RAW_CONTEXT_LEAKED" in reasons


def test_query_echo_removal_prevents_false_leak():
    c = case().model_copy(update={"query": "CANARY_FIN"})
    findings, reasons, warnings = detect_leakage(c, ExtractedResponse(answer_text="CANARY_FIN"), {"leakage": {"remove_query_echo_before_check": True}})
    assert not findings
    assert "QUERY_CONTAINED_FORBIDDEN_TEXT" in warnings


def test_forbidden_query_with_no_leakage_pass_evidence_absent_reasons():
    findings, reasons, _ = detect_leakage(case(), ExtractedResponse(answer_text="no results"), {})
    assert not findings
    assert "FORBIDDEN_CANARY_NOT_FOUND" in reasons
