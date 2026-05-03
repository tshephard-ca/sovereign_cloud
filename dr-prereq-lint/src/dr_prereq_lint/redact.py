"""Redaction for shareable output files."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

from .models import Finding, ObservedPrerequisite, Summary
from .normalize import normalize_fqdn, normalize_ip, stable_hash


@dataclass
class RedactionContext:
    protected_names: dict[str, str] = field(default_factory=dict)
    prereq_names: dict[str, str] = field(default_factory=dict)

    def system_token(self, value: str) -> str:
        if not value:
            return ""
        if value not in self.protected_names:
            self.protected_names[value] = f"system_{len(self.protected_names) + 1:03d}"
        return self.protected_names[value]

    def prereq_token(self, value: str) -> str:
        if not value:
            return ""
        if value not in self.prereq_names:
            self.prereq_names[value] = f"prereq_{len(self.prereq_names) + 1:03d}"
        return self.prereq_names[value]


def redact_outputs(
    findings: list[Finding],
    observed: list[ObservedPrerequisite],
    summary: Summary,
) -> tuple[list[Finding], list[ObservedPrerequisite], Summary]:
    ctx = RedactionContext()
    redacted_findings = [_redact_finding(item, ctx) for item in findings]
    redacted_observed = [_redact_observed(item, ctx) for item in observed]
    redacted_summary = summary.model_copy(deep=True)
    redacted_summary.top_missing_prerequisites = [ctx.prereq_token(value) for value in summary.top_missing_prerequisites]
    return redacted_findings, redacted_observed, redacted_summary


def _redact_finding(finding: Finding, ctx: RedactionContext) -> Finding:
    item = finding.model_copy(deep=True)
    item.prerequisite_name = ctx.prereq_token(item.prerequisite_name)
    item.prerequisite_target = redact_name_shape(item.prerequisite_target)
    item.prerequisite_target_ip = redact_ip(item.prerequisite_target_ip)
    item.example_protected_systems = [ctx.system_token(value) for value in item.example_protected_systems]
    item.example_qnames = [redact_name_shape(value) for value in item.example_qnames]
    item.example_answer_names = [redact_name_shape(value) for value in item.example_answer_names]
    item.example_answer_ips = [redact_ip(value) for value in item.example_answer_ips]
    return item


def _redact_observed(item: ObservedPrerequisite, ctx: RedactionContext) -> ObservedPrerequisite:
    redacted = item.model_copy(deep=True)
    redacted.prerequisite_name = ctx.prereq_token(redacted.prerequisite_name)
    redacted.prerequisite_target = redact_name_shape(redacted.prerequisite_target)
    redacted.prerequisite_target_ip = redact_ip(redacted.prerequisite_target_ip)
    return redacted


def redact_ip(value: str) -> str:
    ip_text = normalize_ip(value)
    if not ip_text:
        return ""
    ip = ipaddress.ip_address(ip_text)
    if ip.version == 4:
        octets = ip_text.split(".")
        if octets[0] == "10":
            return "private_10_x"
        if octets[0] == "172" and 16 <= int(octets[1]) <= 31:
            return "private_172_16_x"
        if octets[0] == "192" and octets[1] == "168":
            return "private_192_168_x"
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return "private_ip_hash_" + stable_hash(ip_text)
    return "public_ip_hash_" + stable_hash(ip_text)


def redact_name_shape(value: str) -> str:
    name = normalize_fqdn(value)
    if not name:
        return ""
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", name):
        return redact_ip(name)
    labels = name.split(".")
    first = labels[0]
    first = re.sub(r"\d+", "{n}", first)
    if first.startswith("_"):
        first = re.sub(r"_[a-z0-9-]+", "_service", first, count=1)
    if len(labels) >= 3:
        return f"{first}.{labels[1]}.{{domain}}"
    if len(labels) == 2:
        return f"{first}.{{domain}}"
    return f"{first}_{stable_hash(name, 6)}"
