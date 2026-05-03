from __future__ import annotations

import hashlib
import ipaddress
import re
from typing import Any

from .validators import is_rfc1918_ip


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_token(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def redact_ip(value: str) -> str | None:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return None
    if is_rfc1918_ip(value):
        if value.startswith("10."):
            return "private_10_x"
        if value.startswith("172."):
            return "private_172_16_x"
        if value.startswith("192.168."):
            return "private_192_168_x"
    return hash_token("public_ip_hash", value)


def redact_cidr(value: str) -> str | None:
    if "/" not in value:
        return None
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError:
        return None
    return hash_token("cidr_hash", value)


def redact_value(value: Any, service_name_map: dict[str, str] | None = None) -> Any:
    if isinstance(value, dict):
        return {redact_value(key, service_name_map) if isinstance(key, str) else key: redact_value(item, service_name_map) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, service_name_map) for item in value]
    if isinstance(value, str):
        if service_name_map and value in service_name_map:
            return service_name_map[value]
        if service_name_map:
            for raw, replacement in sorted(service_name_map.items(), key=lambda item: len(item[0]), reverse=True):
                if raw:
                    value = value.replace(raw, replacement)
        if EMAIL_RE.match(value):
            return "redacted_email"
        cidr = redact_cidr(value)
        if cidr:
            return cidr
        ip = redact_ip(value)
        if ip:
            return ip
    return value


def service_display_name_map(names: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for index, name in enumerate(sorted(set(filter(None, names))), start=1):
        mapping[name] = f"service_{index:03d}"
    return mapping
