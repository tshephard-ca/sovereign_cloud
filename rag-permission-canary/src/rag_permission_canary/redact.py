"""Deterministic redaction helpers."""

from __future__ import annotations

import hashlib
import re

from .models import RunResults


def stable_hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def redact_text(value: str, *, max_chars: int = 120) -> str:
    text = str(value or "")
    text = re.sub(r"CANARY_[A-Z0-9_\\-]+", lambda m: "canary_hash_" + stable_hash(m.group(0)), text)
    text = re.sub(r"[A-Z]+-[A-Z0-9\\-]+", lambda m: m.group(0).split("-", 1)[0] + "-<REDACTED>", text)
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return text


def redact_id(value: str, prefix: str) -> str:
    return f"{prefix}_hash_{stable_hash(value)}" if value else ""


def redact_results(results: RunResults) -> RunResults:
    redacted = results.model_copy(deep=True)
    user_map: dict[str, str] = {}
    doc_map: dict[str, str] = {}
    for idx, item in enumerate(sorted({result.user_id for result in redacted.test_results}), start=1):
        user_map[item] = f"user_{idx:03d}"
    for result in redacted.test_results:
        result.user_id = user_map.get(result.user_id, result.user_id)
        if result.target_doc_id:
            doc_map.setdefault(result.target_doc_id, f"doc_{len(doc_map)+1:03d}")
            result.target_doc_id = doc_map[result.target_doc_id]
        result.citation_doc_ids_redacted = [doc_map.setdefault(doc, f"doc_{len(doc_map)+1:03d}") for doc in result.citation_doc_ids_redacted]
        result.answer_excerpt_redacted = redact_text(result.answer_excerpt_redacted)
        for finding in result.leakage_findings:
            if finding.forbidden_doc_id:
                doc_map.setdefault(finding.forbidden_doc_id, f"doc_{len(doc_map)+1:03d}")
                finding.forbidden_doc_id = doc_map[finding.forbidden_doc_id]
            finding.redacted_evidence = redact_text(finding.redacted_evidence)
    return redacted
