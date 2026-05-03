from __future__ import annotations

import os
from urllib.parse import urlparse

from .constraints import declared_location_reason_codes
from .models import Constraints, EndpointProfile, WorkloadProfile


AUTH_HEADER_NAMES = {"authorization", "x-api-key", "api-key", "proxy-authorization"}
MVP_WORKLOAD_TYPES = {"chat_text", "completion_text", "embedding"}


def validate_endpoint_url(endpoint: EndpointProfile, config: dict) -> tuple[bool, list[str], list[str]]:
    warnings: list[str] = []
    parsed = urlparse(endpoint.base_url)
    if not parsed.scheme or not parsed.netloc:
        return False, ["ENDPOINT_URL_INVALID"], warnings
    if parsed.scheme == "https":
        return True, [], warnings
    host = parsed.hostname or ""
    allow_local = config.get("http", {}).get("allow_http_local_lab", False)
    local_host = host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".invalid")
    if parsed.scheme == "http" and allow_local and local_host:
        warnings.append("HTTP_LAB_MODE_USED")
        return True, [], warnings
    if config.get("http", {}).get("require_https", True):
        return False, ["HTTPS_REQUIRED"], warnings
    return True, [], warnings


def validate_auth_config(endpoint: EndpointProfile, require_credentials: bool) -> tuple[bool, list[str]]:
    if endpoint.auth.type == "none":
        return True, ["AUTH_CONFIG_VALID"]
    if require_credentials and not os.environ.get(endpoint.auth.token_env or ""):
        return False, ["AUTH_ENV_MISSING"]
    return True, ["AUTH_CONFIG_VALID"]


def validate_request_overrides(endpoint: EndpointProfile) -> tuple[bool, list[str]]:
    if not endpoint.request_overrides:
        return True, []
    for name in endpoint.request_overrides.headers:
        if name.lower() in AUTH_HEADER_NAMES:
            return False, ["ENDPOINT_PROFILE_INVALID"]
    return True, []


def endpoint_eligibility(
    endpoint: EndpointProfile,
    workload: WorkloadProfile,
    constraints: Constraints,
    config: dict,
    strict: bool = False,
) -> tuple[bool, list[str], list[str]]:
    eligible = True
    codes: list[str] = []
    warnings: list[str] = ["DECLARED_LOCATION_NOT_VERIFIED"]

    url_ok, url_codes, url_warnings = validate_endpoint_url(endpoint, config)
    warnings.extend(url_warnings)
    codes.extend(url_codes)
    if not url_ok:
        eligible = False

    override_ok, override_codes = validate_request_overrides(endpoint)
    codes.extend(override_codes)
    if not override_ok:
        eligible = False

    auth_ok, auth_codes = validate_auth_config(endpoint, require_credentials=strict)
    codes.extend(auth_codes)
    if not auth_ok:
        eligible = False

    if workload.workload_type in endpoint.capabilities.workload_types:
        codes.append("WORKLOAD_TYPE_SUPPORTED")
    else:
        codes.append("WORKLOAD_TYPE_NOT_SUPPORTED")
        eligible = False

    if workload.workload_type not in MVP_WORKLOAD_TYPES:
        codes.append("WORKLOAD_TYPE_NOT_IMPLEMENTED")
        eligible = False

    if workload.model.streaming_required:
        if endpoint.capabilities.streaming and endpoint.response_mode == "streaming":
            codes.append("STREAMING_SUPPORTED")
        else:
            codes.append("STREAMING_REQUIRED_NOT_SUPPORTED")
            eligible = False
    else:
        codes.append("STREAMING_SUPPORTED" if endpoint.capabilities.streaming else "STREAMING_NOT_REQUIRED")

    required_context = workload.model.min_context_window_tokens
    max_context = endpoint.capabilities.max_context_window_tokens
    if required_context is not None and max_context is not None and required_context > max_context:
        codes.append("CONTEXT_WINDOW_TOO_SMALL")
        eligible = False
    else:
        codes.append("CONTEXT_WINDOW_SUFFICIENT")

    expected_output = workload.model.expected_output_tokens_p95
    max_output = endpoint.capabilities.max_output_tokens
    if expected_output is not None and max_output is not None and expected_output > max_output:
        codes.append("OUTPUT_TOKEN_LIMIT_TOO_SMALL")
        if strict:
            eligible = False
    else:
        codes.append("OUTPUT_TOKEN_LIMIT_SUFFICIENT")

    location_ok, location_codes = declared_location_reason_codes(endpoint.declared_location, constraints)
    codes.extend(location_codes)
    if not location_ok:
        eligible = False

    codes.append("ENDPOINT_ELIGIBLE" if eligible else "ENDPOINT_INELIGIBLE")
    return eligible, _unique_preserve(codes), _unique_preserve(warnings)


def _unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out
