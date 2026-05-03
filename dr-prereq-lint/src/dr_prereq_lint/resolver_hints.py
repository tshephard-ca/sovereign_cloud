"""Resolver hint YAML loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import ResolverHint
from .normalize import normalize_fqdn, normalize_ip_list


def load_resolver_hints(path: str | Path | None, *, strict: bool = False) -> tuple[list[ResolverHint], list[str]]:
    if path is None:
        return [], []
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    warnings: list[str] = []
    if not isinstance(data, dict):
        raise ValueError("resolver hints must be a YAML mapping")
    hints: list[ResolverHint] = []
    for idx, item in enumerate(data.get("resolvers", []) or [], start=1):
        if not isinstance(item, dict):
            if strict:
                raise ValueError("resolver hint entries must be mappings")
            warnings.append("INVALID_RESOLVER_HINT")
            continue
        name = normalize_fqdn(item.get("name"))
        ips = normalize_ip_list("|".join(str(ip) for ip in item.get("ip_addresses", []) or []))
        if not name and not ips:
            if strict:
                raise ValueError("resolver hint must include name or ip_addresses")
            warnings.append("INVALID_RESOLVER_HINT")
            continue
        hints.append(
            ResolverHint(
                name=name,
                ip_addresses=ips,
                recovery_required=bool(item.get("recovery_required", True)),
                source_row=idx,
            )
        )
    return hints, warnings
