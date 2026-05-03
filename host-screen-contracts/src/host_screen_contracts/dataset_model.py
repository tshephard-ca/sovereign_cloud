from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


MaturityLevel = Literal["L0", "L1", "L2", "L3", "L4", "L5", "L6"]
EvidenceKind = Literal[
    "deterministic_synthetic",
    "domain_realistic_synthetic",
    "sanitized_local_capture",
    "real_structure_tokenized",
    "real_multi_case",
    "real_drift",
    "portfolio_metrics",
]
CasePurpose = Literal[
    "canonical_success",
    "canonical_error",
    "drift_evidence",
    "navigation",
    "non_contract",
    "guardrail",
    "recorded_path",
]


class DatasetCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace: str
    purpose: CasePurpose = "recorded_path"
    case_kind: str | None = None
    description: str = ""


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    package_id: str
    transaction_id: str
    maturity_level: MaturityLevel = "L0"
    evidence_kind: EvidenceKind | None = None
    actual_maturity_level: MaturityLevel | None = None
    simulates_maturity_level: MaturityLevel | None = None
    description: str = ""
    traces: dict[str, str] = Field(default_factory=dict)
    cases: dict[str, DatasetCase] = Field(default_factory=dict)
    field_map: str | None = None
    replay_cases: dict[str, str] = Field(default_factory=dict)
    expected_contract: str | None = None
    expected_openapi: str | None = None
    expected_summary: str | None = None
    tags: list[str] = Field(default_factory=list)


def infer_case_purpose(case_id: str) -> CasePurpose:
    lowered = case_id.lower()
    if any(token in lowered for token in ("label_drift", "field_move_drift", "attribute_drift")):
        return "drift_evidence"
    if "cancel" in lowered:
        return "non_contract"
    if "low_confidence" in lowered:
        return "guardrail"
    if any(token in lowered for token in ("not_found", "validation_error", "permission_denied", "invalid_date")):
        return "canonical_error"
    if any(token in lowered for token in ("navigation", "menu")):
        return "navigation"
    if "happy" in lowered or any(token in lowered for token in ("blank_optional", "max_length", "negative_amount", "locale_variant", "screen_27x132")):
        return "canonical_success"
    return "recorded_path"


def infer_case_kind(case_id: str) -> str:
    lowered = case_id.lower()
    for token in (
        "not_found",
        "validation_error",
        "permission_denied",
        "invalid_date",
        "cancel",
        "label_drift",
        "field_move_drift",
        "attribute_drift",
        "unsupported_aid",
        "happy_path",
    ):
        if token in lowered:
            return token
    return "recorded_path"


def manifest_cases(manifest: DatasetManifest) -> dict[str, DatasetCase]:
    if manifest.cases:
        return manifest.cases
    return {
        case_id: DatasetCase(
            trace=trace,
            purpose=infer_case_purpose(case_id),
            case_kind=infer_case_kind(case_id),
        )
        for case_id, trace in manifest.traces.items()
    }


def init_dataset_package(package_dir: str | Path, *, transaction_id: str, maturity_level: MaturityLevel = "L0") -> DatasetManifest:
    root = Path(package_dir)
    for child in ("traces", "field_maps", "cases", "expected", "review", "privacy", "provenance"):
        (root / child).mkdir(parents=True, exist_ok=True)
    manifest = DatasetManifest(
        package_id=transaction_id,
        transaction_id=transaction_id,
        maturity_level=maturity_level,
        evidence_kind="deterministic_synthetic" if maturity_level in {"L0", "L1"} else None,
        traces={"happy_path": "traces/happy_path.trace.jsonl"},
        cases={
            "happy_path": DatasetCase(
                trace="traces/happy_path.trace.jsonl",
                purpose="canonical_success",
                case_kind="happy_path",
            )
        },
        field_map="field_maps/transaction.fields.yml",
    )
    (root / "manifest.yml").write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False))
    return manifest


def load_dataset_manifest(package_dir: str | Path) -> DatasetManifest:
    root = Path(package_dir)
    data = yaml.safe_load((root / "manifest.yml").read_text()) or {}
    return DatasetManifest(**data)
