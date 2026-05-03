"""Policy change-impact reporting."""

from __future__ import annotations

from pydantic import BaseModel, Field

from estate_triage.assessment import AssessmentResult
from estate_triage.config import Thresholds
from estate_triage.policy import PolicyPack, choose_winning_motion, evaluate_policy


class WorkloadPolicyDelta(BaseModel):
    workload_id: str
    workload_key: str
    baseline_motion: str
    candidate_motion: str
    baseline_score: int
    candidate_score: int
    score_delta: int


class PolicyImpactReport(BaseModel):
    workload_count: int
    changed_primary_motion: int = 0
    score_changes: int = 0
    average_score_delta: float = 0.0
    deltas: list[WorkloadPolicyDelta] = Field(default_factory=list)


def policy_change_impact(
    assessment: AssessmentResult,
    *,
    baseline_policy: PolicyPack,
    candidate_policy: PolicyPack,
    thresholds: Thresholds | None = None,
) -> PolicyImpactReport:
    active_thresholds = thresholds or Thresholds()
    deltas: list[WorkloadPolicyDelta] = []
    for workload in assessment.workloads:
        baseline = choose_winning_motion(
            evaluate_policy(
                workload.identity,
                workload.feature_set,
                active_thresholds,
                policy_pack=baseline_policy,
            )
        )
        candidate = choose_winning_motion(
            evaluate_policy(
                workload.identity,
                workload.feature_set,
                active_thresholds,
                policy_pack=candidate_policy,
            )
        )
        if baseline.motion != candidate.motion or baseline.score != candidate.score:
            deltas.append(
                WorkloadPolicyDelta(
                    workload_id=workload.workload_id,
                    workload_key=workload.workload_key,
                    baseline_motion=baseline.motion,
                    candidate_motion=candidate.motion,
                    baseline_score=baseline.score,
                    candidate_score=candidate.score,
                    score_delta=candidate.score - baseline.score,
                )
            )
    average_delta = (
        round(sum(delta.score_delta for delta in deltas) / len(deltas), 3)
        if deltas
        else 0.0
    )
    return PolicyImpactReport(
        workload_count=len(assessment.workloads),
        changed_primary_motion=sum(
            1 for delta in deltas if delta.baseline_motion != delta.candidate_motion
        ),
        score_changes=len(deltas),
        average_score_delta=average_delta,
        deltas=deltas,
    )
