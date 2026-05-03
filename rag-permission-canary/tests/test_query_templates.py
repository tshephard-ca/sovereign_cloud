from rag_permission_canary.models import Document
from rag_permission_canary.query_templates import allowed_query, forbidden_query


def test_allowed_template_can_include_canary():
    doc = Document(doc_id="d1", title="Title", collection="c", body="body")
    assert "CANARY_X" in allowed_query(doc, "CANARY_X", 0)


def test_forbidden_template_does_not_require_canary():
    doc = Document(doc_id="d1", title="Title", collection="finance", body="body")
    assert "CANARY" not in forbidden_query(doc, 0)
