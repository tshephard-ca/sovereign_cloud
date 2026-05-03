from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import (
    CaseBundleManifest,
    CompatibilitySummary,
    CutoverDecisionBrief,
    PolicyPack,
    ProbePlan,
    ProbeResults,
    Questionnaire,
    RealWorldDataAssessment,
    RedactionReport,
    UsageProfile,
    ValidationResult,
)
from .probe_plan import plan_from_yaml


ARTIFACT_MODELS = {
    "usage-profile": UsageProfile,
    "probe-results": ProbeResults,
    "compat-summary": CompatibilitySummary,
    "cutover-brief": CutoverDecisionBrief,
    "redaction-report": RedactionReport,
    "case": CaseBundleManifest,
    "questionnaire": Questionnaire,
    "policy-pack": PolicyPack,
    "real-world-assessment": RealWorldDataAssessment,
}


def validate_artifact(path: str | Path, artifact_type: str | None = None) -> ValidationResult:
    target = Path(path)
    inferred = artifact_type or infer_artifact_type(target)
    try:
        if inferred == "probe-plan":
            plan_from_yaml(target.read_text(encoding="utf-8"))
        else:
            model = ARTIFACT_MODELS.get(inferred)
            if model is None:
                raise ValueError(f"unsupported artifact type: {inferred}")
            payload = _load_structured(target)
            model(**payload)
        return ValidationResult(status="PASS", artifact_type=inferred, path=str(target))
    except (ValidationError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        return ValidationResult(status="FAIL", artifact_type=inferred, path=str(target), errors=[str(exc)])


def infer_artifact_type(path: Path) -> str:
    name = path.name
    if name.endswith(".yml") or name.endswith(".yaml"):
        if "plan" in name:
            return "probe-plan"
        if name == "case.yml":
            return "case"
        if "question" in name:
            return "questionnaire"
        if "policy" in name:
            return "policy-pack"
    if "usage-profile" in name:
        return "usage-profile"
    if "probe-results" in name:
        return "probe-results"
    if "compat-summary" in name:
        return "compat-summary"
    if "cutover-brief" in name:
        return "cutover-brief"
    if "redaction-report" in name:
        return "redaction-report"
    return "usage-profile"


def schema_for(artifact_type: str) -> dict[str, Any]:
    if artifact_type == "probe-plan":
        return ProbePlan.model_json_schema()
    model = ARTIFACT_MODELS.get(artifact_type)
    if model is None:
        raise ValueError(f"unsupported artifact type: {artifact_type}")
    return model.model_json_schema()


def _load_structured(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yml", ".yaml"}:
        loaded = yaml.safe_load(text) or {}
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("artifact root must be a mapping")
    return loaded
