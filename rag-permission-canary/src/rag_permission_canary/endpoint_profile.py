"""Endpoint profile loading, validation, and request templating."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .models import CanaryTestCase, EndpointProfile, TestUser


PLACEHOLDERS = {
    "query",
    "user_id",
    "test_case_id",
    "expected_allowed_doc_ids",
    "expected_forbidden_doc_ids",
}


def load_endpoint_profile(path: str | Path, *, strict: bool = False) -> EndpointProfile:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    profile = EndpointProfile.model_validate(payload)
    validate_endpoint_profile(profile, strict=strict)
    return profile


def validate_endpoint_profile(profile: EndpointProfile, *, strict: bool = False) -> None:
    parsed = urlparse(profile.base_url)
    if not profile.endpoint_id:
        raise ValueError("ENDPOINT_INVALID")
    if parsed.scheme == "https":
        pass
    elif profile.local_test_only and (parsed.hostname in {"localhost", "127.0.0.1"} or str(parsed.hostname or "").endswith(".invalid")):
        pass
    else:
        raise ValueError("HTTPS_REQUIRED")
    if not profile.request.body_template:
        raise ValueError("endpoint request.body_template is required")
    unknown = sorted(set(_find_placeholders(profile.request.body_template)) - PLACEHOLDERS)
    if unknown:
        raise ValueError(f"unknown endpoint template placeholder: {unknown[0]}")
    if strict and profile.auth.user_auth_from_test_user is False and profile.auth.type == "none":
        raise ValueError("ENDPOINT_INVALID")


def render_body_template(profile: EndpointProfile, test_case: CanaryTestCase, user: TestUser) -> dict:
    replacements = {
        "query": test_case.query,
        "user_id": user.user_id,
        "test_case_id": test_case.test_case_id,
        "expected_allowed_doc_ids": ",".join(test_case.allowed_doc_ids),
        "expected_forbidden_doc_ids": ",".join(test_case.forbidden_doc_ids),
    }
    return _render_value(profile.request.body_template, replacements)


def endpoint_url(profile: EndpointProfile) -> str:
    return profile.base_url.rstrip("/") + "/" + profile.request.path.lstrip("/")


def _find_placeholders(value: object) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            result.extend(_find_placeholders(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(_find_placeholders(item))
    elif isinstance(value, str):
        result.extend(re.findall(r"{{\s*([a-zA-Z0-9_]+)\s*}}", value))
    return result


def _render_value(value: object, replacements: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {key: _render_value(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_value(item, replacements) for item in value]
    if isinstance(value, str):
        rendered = value
        for key, replacement in replacements.items():
            rendered = re.sub(r"{{\s*" + re.escape(key) + r"\s*}}", replacement, rendered)
        return rendered
    return value
