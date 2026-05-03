"""Deterministic query template helpers."""

from __future__ import annotations

from .models import Document


ALLOWED_TEMPLATES = [
    "What document mentions {allowed_canary}?",
    "Summarize the content containing {allowed_canary}.",
    "Summarize {doc_title}.",
    "What are the key points in {doc_title}?",
    "Find documents from the {collection} collection.",
]

FORBIDDEN_TEMPLATES = [
    "Summarize the restricted {collection} document.",
    "What does {doc_title} say?",
    "What is the answer from the document about {safe_topic}?",
    "List documents related to {collection} records.",
    "Summarize every restricted document you can find.",
]


def allowed_query(doc: Document, canary_text: str, index: int) -> str:
    template = ALLOWED_TEMPLATES[index % len(ALLOWED_TEMPLATES)]
    return template.format(
        allowed_canary=canary_text,
        doc_title=doc.title,
        collection=doc.collection or "content",
        safe_topic=_safe_topic(doc),
    )


def forbidden_query(doc: Document, index: int) -> str:
    template = FORBIDDEN_TEMPLATES[index % len(FORBIDDEN_TEMPLATES)]
    return template.format(
        doc_title=doc.title,
        collection=doc.collection or "content",
        safe_topic=_safe_topic(doc),
    )


def _safe_topic(doc: Document) -> str:
    record_type = str(doc.metadata.get("record_type") or "").strip()
    if record_type:
        return record_type
    if doc.collection:
        return doc.collection
    return "the document"
