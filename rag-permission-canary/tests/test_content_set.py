import pytest

from rag_permission_canary.content_set import load_content_set


def test_parses_valid_content_set(write_yaml, base_content):
    content = load_content_set(write_yaml("content.yml", base_content))
    assert content.content_set_id == "test_content"
    assert len(content.documents) == 3


def test_fails_duplicate_doc_id(write_yaml, base_content):
    base_content["documents"][1]["doc_id"] = "doc_hr"
    with pytest.raises(ValueError, match="duplicate doc_id"):
        load_content_set(write_yaml("content.yml", base_content))


def test_fails_non_unique_canary_text(write_yaml, base_content):
    base_content["documents"][1]["canaries"][0]["text"] = "CANARY_HR_ALPHA"
    with pytest.raises(ValueError, match="canary text"):
        load_content_set(write_yaml("content.yml", base_content))
