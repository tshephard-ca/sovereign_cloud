"""Assessment comparison helpers for repeated local runs."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from estate_triage.assessment import AssessmentResult
from estate_triage.models import TriageError


class AssessmentComparison(BaseModel):
    baseline: str
    current: str
    baseline_workloads: int
    current_workloads: int
    workload_delta: int
    motion_delta: dict[str, int]
    confidence_delta: dict[str, int]
    identity_status_delta: dict[str, int]
    added_workload_keys: list[str]
    removed_workload_keys: list[str]


def load_assessment_json(path: Path) -> AssessmentResult:
    try:
        return AssessmentResult.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TriageError(f"Invalid assessment JSON {path}: {exc}") from exc


def _delta(left: Counter[str], right: Counter[str]) -> dict[str, int]:
    keys = sorted(set(left) | set(right))
    return {key: right.get(key, 0) - left.get(key, 0) for key in keys}


def compare_assessments(
    baseline_path: Path,
    current_path: Path,
) -> AssessmentComparison:
    baseline = load_assessment_json(baseline_path)
    current = load_assessment_json(current_path)
    baseline_keys = {workload.workload_key for workload in baseline.workloads}
    current_keys = {workload.workload_key for workload in current.workloads}
    return AssessmentComparison(
        baseline=str(baseline_path),
        current=str(current_path),
        baseline_workloads=len(baseline.workloads),
        current_workloads=len(current.workloads),
        workload_delta=len(current.workloads) - len(baseline.workloads),
        motion_delta=_delta(
            Counter(workload.winning_motion.motion for workload in baseline.workloads),
            Counter(workload.winning_motion.motion for workload in current.workloads),
        ),
        confidence_delta=_delta(
            Counter(workload.confidence for workload in baseline.workloads),
            Counter(workload.confidence for workload in current.workloads),
        ),
        identity_status_delta=_delta(
            Counter(workload.identity.status for workload in baseline.workloads),
            Counter(workload.identity.status for workload in current.workloads),
        ),
        added_workload_keys=sorted(current_keys - baseline_keys),
        removed_workload_keys=sorted(baseline_keys - current_keys),
    )
