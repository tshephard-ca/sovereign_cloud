"""Known prerequisite rule loading and matching."""

from __future__ import annotations

from pathlib import Path
import re

from pydantic import BaseModel, Field
import yaml

from .models import KnownPrereqRule, SUPPORTED_CATEGORIES
from .normalize import normalize_fqdn, normalize_fqdn_list


class KnownPrereqSet(BaseModel):
    internal_domains: list[str] = Field(default_factory=list)
    prerequisites: list[KnownPrereqRule] = Field(default_factory=list)

    def matches(self, qname: str) -> list[KnownPrereqRule]:
        normalized = normalize_fqdn(qname)
        matches: list[KnownPrereqRule] = []
        for rule in self.prerequisites:
            if normalized in rule.names:
                matches.append(rule)
                continue
            if any(re.search(pattern, normalized) for pattern in rule.qname_regex):
                matches.append(rule)
        return matches


def load_known_prereqs(path: str | Path | None) -> KnownPrereqSet:
    if path is None:
        return KnownPrereqSet()
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("known prerequisites must be a YAML mapping")
    internal_domains = normalize_fqdn_list("|".join(str(domain) for domain in data.get("internal_domains", []) or []))
    rules: list[KnownPrereqRule] = []
    for idx, item in enumerate(data.get("prerequisites", []) or [], start=1):
        if not isinstance(item, dict):
            raise ValueError("known prerequisite entries must be mappings")
        category = str(item.get("category", "")).strip()
        if category not in SUPPORTED_CATEGORIES:
            raise ValueError(f"unknown prerequisite category: {category}")
        regexes = [str(pattern) for pattern in item.get("qname_regex", []) or []]
        for pattern in regexes:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid known prerequisite regex {pattern!r}: {exc}") from exc
        rules.append(
            KnownPrereqRule(
                id=str(item.get("id") or f"known_{idx}"),
                display_name=str(item.get("display_name") or item.get("id") or f"Known prerequisite {idx}"),
                category=category,
                names=normalize_fqdn_list("|".join(str(name) for name in item.get("names", []) or [])),
                qname_regex=regexes,
                required_in_recovery_set=bool(item.get("required_in_recovery_set", True)),
                source_row=idx,
            )
        )
    return KnownPrereqSet(internal_domains=internal_domains, prerequisites=rules)
