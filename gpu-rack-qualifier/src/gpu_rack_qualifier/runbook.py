from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_yaml


def load_runbook(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = load_yaml(path)
    base = path.parent
    outputs = data.get("outputs") or {}
    output_dir = _resolve(base, outputs.get("dir", "out"))
    return {
        "evidence": _resolve(base, data.get("evidence")) if data.get("evidence") else None,
        "node_inventory": _resolve(base, data.get("node_inventory")) if data.get("node_inventory") else None,
        "policy": _resolve(base, data.get("policy")) if data.get("policy") else None,
        "business_assumptions": _resolve(base, data.get("business_assumptions")) if data.get("business_assumptions") else None,
        "outputs": {
            "labels": _resolve_output(base, output_dir, outputs.get("labels", "slurm_node_labels.csv")),
            "quarantine": _resolve_output(base, output_dir, outputs.get("quarantine", "quarantine.csv")),
            "review_queue": _resolve_output(base, output_dir, outputs.get("review_queue", "review_queue.csv")),
            "slurm_fragment": _resolve_output(base, output_dir, outputs.get("slurm_fragment", "slurm_features.conf.snippet")),
            "drain_review": _resolve_output(base, output_dir, outputs.get("drain_review", "drain_review.sh")),
            "summary": _resolve_output(base, output_dir, outputs.get("summary", "summary.json")),
            "evidence_bundle": _resolve_output(base, output_dir, outputs.get("evidence_bundle", "evidence_bundle.json")),
        },
    }


def value_from_runbook(runbook: dict[str, Any], key: str, current):
    return current if current is not None else runbook.get(key)


def output_from_runbook(runbook: dict[str, Any], key: str, current):
    if current is not None:
        return current
    return (runbook.get("outputs") or {}).get(key)


def _resolve(base: Path, value) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _resolve_output(base: Path, output_dir: Path, value) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    if len(path.parts) > 1:
        return base / path
    return output_dir / path
