"""Generic HTTP execution for canary test cases."""

from __future__ import annotations

import json
import time

import httpx

from .endpoint_profile import endpoint_url, render_body_template
from .models import CanaryTestCase, EndpointProfile, EndpointResponse, TestUser
from .users import auth_headers_for_user


def send_test_request(
    *,
    profile: EndpointProfile,
    test_case: CanaryTestCase,
    user: TestUser,
    timeout_seconds: int,
    strict: bool = False,
    dry_run: bool = False,
    no_network: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> tuple[EndpointResponse, list[str]]:
    reason_codes: list[str] = []
    if dry_run:
        return EndpointResponse(error="dry run", warnings=["DRY_RUN_ONLY"]), ["DRY_RUN_ONLY"]
    if no_network:
        return EndpointResponse(error="network disabled", warnings=["NO_NETWORK_MODE"]), ["NO_NETWORK_MODE"]
    headers = dict(profile.request.headers)
    auth_headers, auth_warnings, auth_reasons = auth_headers_for_user(user, strict=strict)
    headers.update(auth_headers)
    reason_codes.extend(auth_reasons)
    body = render_body_template(profile, test_case, user)
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
            response = client.request(profile.request.method.upper(), endpoint_url(profile), headers=headers, json=body)
        latency = int((time.perf_counter() - started) * 1000)
        reason_codes.extend(["ENDPOINT_REQUEST_SENT", "ENDPOINT_RESPONSE_RECEIVED"])
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = None
        warnings = list(auth_warnings)
        if response.status_code in {401, 403}:
            reason_codes.append("HTTP_AUTH_FAILURE")
        elif response.is_error:
            reason_codes.append("HTTP_ERROR")
        return EndpointResponse(http_status=response.status_code, latency_ms=latency, json_body=payload, text_body=response.text, warnings=warnings), reason_codes
    except httpx.TimeoutException:
        return EndpointResponse(error="request timeout", warnings=["REQUEST_TIMEOUT"]), ["REQUEST_TIMEOUT"]
    except httpx.HTTPError as exc:
        return EndpointResponse(error=str(exc), warnings=["HTTP_ERROR"]), ["HTTP_ERROR"]
