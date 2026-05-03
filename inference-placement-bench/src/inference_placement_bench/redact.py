from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from .models import DeclaredLocation, EndpointProfile


SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)=?[a-z0-9._~+/=-]+"),
    re.compile(r"https?://\S+"),
]


def hash_12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def redact_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = "https" if parsed.scheme == "https" else "scheme_redacted"
    host = parsed.hostname or "unknown"
    return f"{scheme}://host_hash_{hash_12(host)}"


def redact_text(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redacted_display_name(index: int) -> str:
    return f"endpoint_{index + 1:03d}"


def redacted_location(location: DeclaredLocation | None, index: int, preserve: bool = False) -> DeclaredLocation | None:
    if location is None or preserve:
        return location
    return DeclaredLocation(
        country=location.country,
        region=f"zone_{index + 1:03d}" if location.region else None,
        data_zone=f"zone_{index + 1:03d}" if location.data_zone else None,
        operator_control=location.operator_control,
    )


def redact_endpoint_for_plan(endpoint: EndpointProfile, index: int, preserve_location_labels: bool = False) -> dict:
    return {
        "display_name": redacted_display_name(index),
        "base_url_redacted": redact_url(endpoint.base_url),
        "declared_location": redacted_location(endpoint.declared_location, index, preserve_location_labels),
    }
