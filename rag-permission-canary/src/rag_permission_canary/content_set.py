"""Content-set YAML parsing and validation."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import ContentSet, Document


def load_content_set(path: str | Path, *, strict: bool = False) -> ContentSet:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    content = ContentSet.model_validate(payload)
    validate_content_set(content, strict=strict)
    return content


def validate_content_set(content: ContentSet, *, strict: bool = False) -> list[str]:
    blockers: list[str] = []
    if not content.documents:
        blockers.append("NO_DOCUMENTS")
    doc_ids = [doc.doc_id for doc in content.documents]
    if len(doc_ids) != len(set(doc_ids)):
        blockers.append("CONTENT_SET_INVALID")
        raise ValueError("duplicate doc_id in content set")
    canary_texts = [canary.text for doc in content.documents for canary in doc.canaries]
    if not canary_texts:
        blockers.append("NO_CANARIES")
        if strict:
            raise ValueError("content set has no canaries")
    if len(canary_texts) != len(set(canary_texts)):
        blockers.append("CANARY_TEXT_NOT_UNIQUE")
        raise ValueError("canary text must be unique across content set")
    for doc in content.documents:
        if not doc.title or not doc.body:
            raise ValueError(f"document {doc.doc_id} requires title and body")
    return blockers


def document_by_id(content: ContentSet) -> dict[str, Document]:
    return {doc.doc_id: doc for doc in content.documents}


def canary_text_by_id(content: ContentSet) -> dict[str, str]:
    return {canary.canary_id: canary.text for doc in content.documents for canary in doc.canaries}
