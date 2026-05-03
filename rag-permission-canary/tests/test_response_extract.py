from rag_permission_canary.endpoint_profile import load_endpoint_profile
from rag_permission_canary.response_extract import extract_response, json_path


def test_response_extractor_reads_answer_text(write_yaml, endpoint_payload):
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    extracted = extract_response({"answer": "hello"}, endpoint)
    assert extracted.answer_text == "hello"


def test_response_extractor_reads_citations_and_doc_ids(write_yaml, endpoint_payload):
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    extracted = extract_response({"answer": "x", "citations": [{"doc_id": "doc1", "title": "Title", "snippet": "Snippet"}]}, endpoint)
    assert extracted.citations
    assert extracted.citation_doc_ids == ["doc1"]


def test_json_path_supports_wildcard_and_index():
    payload = {"citations": [{"doc_id": "d1"}, {"doc_id": "d2"}]}
    assert json_path(payload, "$.citations[0].doc_id") == ["d1"]
    assert json_path(payload, "$.citations[*].doc_id") == ["d1", "d2"]


def test_response_extractor_handles_missing_citation_fields_with_warning(write_yaml, endpoint_payload):
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    extracted = extract_response({"answer": "x", "citations": [{"doc_id": "doc1"}]}, endpoint)
    assert "RESPONSE_EXTRACTOR_MISSING_FIELD" in extracted.warnings
