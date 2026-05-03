"""Configuration defaults and YAML merge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "default_queries_per_user": 10,
    "default_total_queries": 20,
    "required_allowed_queries": 10,
    "required_forbidden_queries": 10,
    "request_timeout_seconds": 60,
    "require_https": True,
    "allow_http_local_lab": True,
    "user_rule_precedence": False,
    "strict_endpoint_errors_fail": False,
    "allow_review_only": False,
    "generation": {
        "allow_forbidden_token_in_query": False,
        "balance_users": True,
        "balance_documents": True,
        "max_query_length_chars": 300,
    },
    "leakage": {
        "fail_on_forbidden_canary_in_answer": True,
        "fail_on_forbidden_doc_id_in_citation": True,
        "fail_on_forbidden_title": True,
        "fail_on_forbidden_metadata": True,
        "fail_on_forbidden_snippet": True,
        "fail_on_forbidden_raw_context": True,
        "remove_query_echo_before_check": True,
        "case_sensitive_canary_match": True,
        "case_insensitive_title_match": True,
        "max_redacted_evidence_chars": 120,
    },
    "allowed_checks": {
        "require_allowed_evidence": True,
        "require_citations_for_allowed": False,
        "allowed_empty_answer_is_review": True,
    },
    "reporting": {
        "redact_by_default": True,
        "include_raw_answers": False,
        "include_raw_context": False,
        "max_answer_excerpt_chars": 180,
    },
    "business_context": {
        "release_name": "",
        "owner": "",
        "risk_domain": "rag_permission_boundaries",
        "deployment_stage": "",
        "decision_threshold": "fail_blocks_release",
    },
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config = _deep_copy(DEFAULT_CONFIG)
    if path:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        config = _deep_merge(config, payload)
    return config


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value
