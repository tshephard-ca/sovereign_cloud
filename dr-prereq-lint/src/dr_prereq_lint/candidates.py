"""Candidate prerequisite identity helpers."""

from __future__ import annotations

import re

from .models import Finding
from .normalize import normalize_fqdn, stable_hash


def prerequisite_identity(finding: Finding) -> str:
    target = finding.prerequisite_target_ip or normalize_fqdn(finding.prerequisite_target) or normalize_fqdn(finding.prerequisite_name)
    source = "|".join([finding.category, target, finding.finding_code])
    return f"{slug(finding.category)}_{stable_hash(source)}"


def target_display(finding: Finding) -> str:
    return finding.prerequisite_target or finding.prerequisite_target_ip or finding.prerequisite_name


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return text or "item"
