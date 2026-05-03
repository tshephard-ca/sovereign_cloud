from __future__ import annotations

import hashlib
import re
from copy import deepcopy

from .models import NodeInventory, QualificationResult, Summary


def hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def redact_results(results: list[QualificationResult]) -> list[QualificationResult]:
    redacted = deepcopy(results)
    mapping = {result.features.node_name: f"node_{index:03d}" for index, result in enumerate(sorted(redacted, key=lambda item: item.features.node_name), 1)}
    for result in redacted:
        old = result.features.node_name
        new = mapping[old]
        result.features.node_name = new
        result.features.source_evidence = [_replace_all(path, mapping) for path in result.features.source_evidence]
    return redacted


def redact_inventory_identity(inventory: NodeInventory | None) -> NodeInventory | None:
    if inventory is None:
        return None
    redacted = deepcopy(inventory)
    redacted.cluster_id = "cluster_001" if redacted.cluster_id else None
    redacted.rack_id = "rack_001" if redacted.rack_id else None
    for index, node in enumerate(sorted(redacted.nodes, key=lambda item: item.name), 1):
        node.name = f"node_{index:03d}"
        node.rack = "rack_001" if node.rack else None
    return redacted


def redact_summary(summary: Summary) -> Summary:
    redacted = deepcopy(summary)
    redacted.cluster_id = "cluster_001" if redacted.cluster_id else None
    redacted.rack_id = "rack_001" if redacted.rack_id else None
    return redacted


def redact_text(text: str) -> str:
    text = re.sub(r"GPU-[A-Za-z0-9-]+", lambda match: f"GPU-{hash_identifier(match.group(0))}", text)
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", lambda match: hash_identifier(match.group(0)), text)
    return text


def _replace_all(text: str, mapping: dict[str, str]) -> str:
    for old, new in mapping.items():
        text = text.replace(old, new)
    return redact_text(text)
