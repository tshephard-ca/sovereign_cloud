from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .node_inventory import load_node_inventory
from .qualification_policy import load_policy
from .report import LABEL_COLUMNS, QUARANTINE_COLUMNS
from .action_queue import REVIEW_QUEUE_COLUMNS


REQUIRED_SCHEMA_FILES = [
    "qualification_policy.schema.json",
    "node_inventory.schema.json",
    "evidence_bundle.schema.json",
    "summary.schema.json",
    "labels.schema.json",
    "quarantine.schema.json",
    "review_queue.schema.json",
]


def validate_schema_files(schemas_dir: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_SCHEMA_FILES:
        path = schemas_dir / name
        if not path.exists():
            errors.append(f"missing schema file: {path}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON schema document: {exc}")
            continue
        if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{path}: unexpected $schema value")
        if not str(data.get("title", "")).startswith("gpu-rack-qualifier"):
            errors.append(f"{path}: title must start with gpu-rack-qualifier")
        if "type" not in data:
            errors.append(f"{path}: schema has no top-level type")
    return errors


def validate_policy_file(path: Path | None) -> list[str]:
    if path is None:
        return []
    try:
        load_policy(path)
    except Exception as exc:
        return [f"{path}: policy validation failed: {exc}"]
    return []


def validate_inventory_file(path: Path | None) -> list[str]:
    if path is None:
        return []
    try:
        inventory = load_node_inventory(path)
    except Exception as exc:
        return [f"{path}: inventory validation failed: {exc}"]
    errors: list[str] = []
    if inventory:
        names = [node.name for node in inventory.nodes]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            errors.append(f"{path}: duplicate inventory node names: {','.join(duplicates)}")
    return errors


def validate_summary_file(path: Path | None) -> list[str]:
    if path is None:
        return []
    data, error = _load_json(path)
    if error:
        return [error]
    errors: list[str] = []
    required = [
        "cluster_id",
        "rack_id",
        "generated_at",
        "policy_id",
        "mode",
        "input",
        "qualification",
        "labels",
        "blockers",
        "warnings",
        "top_operator_questions",
        "business_impact",
        "readiness",
        "coverage",
        "action_queue_counts",
        "outputs",
    ]
    errors.extend(_missing_keys(path, data, required))
    if data.get("mode") != "REVIEW_ONLY":
        errors.append(f"{path}: mode must be REVIEW_ONLY")
    for key in ["input", "qualification", "labels", "blockers", "business_impact", "readiness", "coverage", "action_queue_counts"]:
        if key in data and not isinstance(data[key], dict):
            errors.append(f"{path}: {key} must be an object")
    return errors


def validate_evidence_bundle_file(path: Path | None) -> list[str]:
    if path is None:
        return []
    data, error = _load_json(path)
    if error:
        return [error]
    errors: list[str] = []
    required = [
        "schema_version",
        "generated_at",
        "tool",
        "mode",
        "redacted",
        "input",
        "nodes",
        "outputs",
        "business_impact",
        "readiness",
        "coverage",
        "action_queue_counts",
    ]
    errors.extend(_missing_keys(path, data, required))
    if data.get("schema_version") != "rackq.evidence_bundle.v1":
        errors.append(f"{path}: schema_version must be rackq.evidence_bundle.v1")
    if data.get("mode") != "REVIEW_ONLY":
        errors.append(f"{path}: mode must be REVIEW_ONLY")
    if not isinstance(data.get("nodes", []), list):
        errors.append(f"{path}: nodes must be a list")
    else:
        for index, node in enumerate(data.get("nodes", []), 1):
            if not isinstance(node, dict):
                errors.append(f"{path}: nodes[{index}] must be an object")
                continue
            errors.extend(_missing_keys(path, node, ["node_name", "files"], prefix=f"nodes[{index}]"))
            for file_index, item in enumerate(node.get("files", []), 1):
                errors.extend(_missing_keys(path, item, ["kind", "path", "sha256", "bytes"], prefix=f"nodes[{index}].files[{file_index}]"))
                sha256 = str(item.get("sha256", ""))
                if sha256 != "REDACTED" and len(sha256) != 64:
                    errors.append(f"{path}: nodes[{index}].files[{file_index}].sha256 must be 64 hex characters or REDACTED")
    return errors


def validate_labels_csv(path: Path | None) -> list[str]:
    return _validate_csv(path, LABEL_COLUMNS, "labels")


def validate_quarantine_csv(path: Path | None) -> list[str]:
    return _validate_csv(path, QUARANTINE_COLUMNS, "quarantine")


def validate_review_queue_csv(path: Path | None) -> list[str]:
    return _validate_csv(path, REVIEW_QUEUE_COLUMNS, "review queue", allow_empty=True)


def validate_review_only_files(slurm_fragment: Path | None = None, drain_review: Path | None = None) -> list[str]:
    errors: list[str] = []
    if slurm_fragment:
        if not slurm_fragment.exists():
            errors.append(f"{slurm_fragment}: file missing")
        else:
            for number, line in enumerate(slurm_fragment.read_text(encoding="utf-8").splitlines(), 1):
                if line and not line.startswith("#"):
                    errors.append(f"{slurm_fragment}:{number}: Slurm fragment line is not commented")
    if drain_review:
        if not drain_review.exists():
            errors.append(f"{drain_review}: file missing")
        else:
            mode = drain_review.stat().st_mode
            if mode & 0o111:
                errors.append(f"{drain_review}: drain review script must not be executable")
            for number, line in enumerate(drain_review.read_text(encoding="utf-8").splitlines(), 1):
                if "scontrol update" in line and not line.startswith("#"):
                    errors.append(f"{drain_review}:{number}: scontrol command must be commented")
    return errors


def validate_artifacts(
    schemas_dir: Path | None = None,
    policy: Path | None = None,
    inventory: Path | None = None,
    summary: Path | None = None,
    labels: Path | None = None,
    quarantine: Path | None = None,
    review_queue: Path | None = None,
    evidence_bundle: Path | None = None,
    slurm_fragment: Path | None = None,
    drain_review: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    if schemas_dir is not None:
        errors.extend(validate_schema_files(schemas_dir))
    errors.extend(validate_policy_file(policy))
    errors.extend(validate_inventory_file(inventory))
    errors.extend(validate_summary_file(summary))
    errors.extend(validate_labels_csv(labels))
    errors.extend(validate_quarantine_csv(quarantine))
    errors.extend(validate_review_queue_csv(review_queue))
    errors.extend(validate_evidence_bundle_file(evidence_bundle))
    errors.extend(validate_review_only_files(slurm_fragment, drain_review))
    return errors


def _validate_csv(path: Path | None, expected_columns: list[str], label: str, allow_empty: bool = False) -> list[str]:
    if path is None:
        return []
    if not path.exists():
        return [f"{path}: {label} CSV missing"]
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected_columns:
            return [f"{path}: {label} CSV columns do not match expected order"]
        row_count = sum(1 for _ in reader)
    if row_count == 0 and not allow_empty:
        return [f"{path}: {label} CSV has no rows"]
    return []


def _load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.exists():
        return {}, f"{path}: file missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"{path}: invalid JSON: {exc}"
    if not isinstance(data, dict):
        return {}, f"{path}: JSON root must be an object"
    return data, None


def _missing_keys(path: Path, data: dict[str, Any], keys: list[str], prefix: str = "") -> list[str]:
    errors: list[str] = []
    for key in keys:
        if key not in data:
            location = f"{prefix}.{key}" if prefix else key
            errors.append(f"{path}: missing required key {location}")
    return errors
