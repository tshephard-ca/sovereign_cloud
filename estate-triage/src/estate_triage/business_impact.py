"""Business-facing interpretation for assessment results.

The assessment kernel stays technical and auditable. This module turns those
facts into deterministic handoff language for discovery, delivery, and account
teams without claiming migration readiness or verified recoverability.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from estate_triage.assessment import AssessmentResult, MissingEvidenceRequest, WorkloadAssessment
from estate_triage.models import PrimaryMotion


PRESENTATION_CLASSES = {
    "strong_candidate",
    "review_candidate",
    "needs_more_data",
    "do_not_present",
}

HIGH_BLOCKERS = {
    "CONFLICTED",
    "DUPLICATE_CANDIDATES",
    "NO_BACKUP_MATCH",
    "MISSING_STORAGE_USED",
}

REVIEW_BLOCKERS = {
    "NAME_MATCH_ONLY",
    "SNAPSHOT_PRESENT",
    "MISSING_CHANGE_RATE",
    "MISSING_BACKUP_SIZE",
    "LOW_CONFIDENCE_RIGHTSIZING",
    "SPARSE_UTILIZATION_WINDOW",
    "POWERED_OFF_NOT_MIGRATION_CANDIDATE",
}

DERIVED_MISSING_EVIDENCE_FIELDS = {
    "backup_to_used_ratio",
    "change_rate_pct",
    "last_powered_on_age_days",
    "last_seen_age_days",
    "snapshot_to_used_ratio",
    "utilization_window_days",
}

MOTION_LABELS: dict[PrimaryMotion, str] = {
    "MIGRATION_REVIEW": "Migration review",
    "ARCHIVE_REVIEW": "Archive review",
    "RIGHTSIZING_REVIEW": "Rightsizing review",
    "DR_TIER_REVIEW": "DR tier review",
}

OWNER_PERSONA: dict[PrimaryMotion, str] = {
    "MIGRATION_REVIEW": "solution architect",
    "ARCHIVE_REVIEW": "application owner",
    "RIGHTSIZING_REVIEW": "platform operations",
    "DR_TIER_REVIEW": "resilience owner",
}

MOTION_IMPACT: dict[PrimaryMotion, str] = {
    "MIGRATION_REVIEW": (
        "This workload has enough protection, identity, and footprint evidence to discuss as a practical migration-review candidate."
    ),
    "ARCHIVE_REVIEW": (
        "This workload looks stale or retired enough to discuss retention, ownership, and whether it should be excluded from active migration scope."
    ),
    "RIGHTSIZING_REVIEW": (
        "This workload has allocation or utilization evidence that can start a capacity review before sizing decisions are made."
    ),
    "DR_TIER_REVIEW": (
        "This workload has backup-footprint or restore-point evidence worth reviewing with the resilience and recovery-tier owners."
    ),
}

MOTION_NEXT_STEP: dict[PrimaryMotion, str] = {
    "MIGRATION_REVIEW": "Put into the migration discovery queue and validate application owner, dependency, and cutover constraints.",
    "ARCHIVE_REVIEW": "Confirm owner, retention requirement, and whether the workload should be archived or removed from active scope.",
    "RIGHTSIZING_REVIEW": "Review utilization window and allocation history before using this workload for sizing assumptions.",
    "DR_TIER_REVIEW": "Review RPO, RTO, retention, and restore-point policy before classifying the recovery tier.",
}

MOTION_QUESTION: dict[PrimaryMotion, str] = {
    "MIGRATION_REVIEW": "Is this workload still active, owned, and suitable for a migration discovery conversation?",
    "ARCHIVE_REVIEW": "Can the owner confirm whether this workload is retired, retained for records, or still business-active?",
    "RIGHTSIZING_REVIEW": "Does the utilization window represent normal business load, seasonal load, or a temporary quiet period?",
    "DR_TIER_REVIEW": "Does application recovery policy require this restore-point count, retention period, and backup footprint?",
}

FIELD_QUESTIONS = {
    "avg_daily_change_mib": "Can the backup export include average daily change so change-rate signals are defensible?",
    "backup_total_mib": "Can the backup export include total protected data size for this workload?",
    "in_use_mib": "Can the inventory export include used storage, not only provisioned storage?",
    "latest_restore_point_utc": "Can the backup export include the most recent restore-point timestamp?",
    "restore_point_count": "Can the backup export include restore-point count?",
    "uuid": "Can the inventory and backup exports include the same workload UUID?",
    "cpu_usage_pct": "Can a utilization export include CPU usage for the selected sample window?",
    "memory_usage_pct": "Can a utilization export include memory usage for the selected sample window?",
    "cpu_p95_pct": "Can the utilization export include CPU p95 for the selected sample window?",
    "memory_p95_pct": "Can the utilization export include memory p95 for the selected sample window?",
    "os": "Can the inventory export include guest OS where known, or confirm that unknown OS is expected for retired workloads?",
    "rpo_hours": "Can the backup export include RPO or policy tier when resilience review is in scope?",
}


class BusinessImpact(BaseModel):
    presentation_class: str
    owner_persona: str
    recommended_next_step: str
    business_question: str
    why_this_matters: str
    evidence_strength: str
    missing_evidence_priority: str
    do_not_present_reason: str | None = None
    motion_fit_explanation: str


def service_context(workload: WorkloadAssessment) -> dict[str, str | None]:
    tags = workload.identity.inventory.tags or ""
    parsed: dict[str, str] = {}
    for raw_part in tags.split(";"):
        if ":" not in raw_part:
            continue
        key, value = raw_part.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()
        if key and value:
            parsed[key] = value
    return {
        "service": parsed.get("service"),
        "declared_motion": parsed.get("motion"),
        "datacenter": workload.identity.inventory.datacenter,
        "cluster": workload.identity.inventory.cluster,
        "host": workload.identity.inventory.host,
        "os": workload.identity.inventory.os,
    }


def _highest_missing_priority(requests: list[MissingEvidenceRequest]) -> str:
    if any(request.priority == "high" for request in requests):
        return "high"
    if requests:
        return "medium"
    return "none"


def presentation_class_for(workload: WorkloadAssessment) -> str:
    blockers = set(workload.blocking_flags)
    if blockers & HIGH_BLOCKERS:
        return "do_not_present"
    high_missing = [request for request in workload.missing_evidence if request.priority == "high"]
    if workload.confidence == "low" or high_missing:
        return "needs_more_data"
    if blockers & REVIEW_BLOCKERS:
        return "review_candidate"
    if workload.confidence == "high":
        return "strong_candidate"
    return "review_candidate"


def evidence_strength_for(workload: WorkloadAssessment) -> str:
    presentation_class = presentation_class_for(workload)
    if presentation_class == "do_not_present":
        return "blocked"
    if presentation_class == "needs_more_data":
        return "weak"
    if presentation_class == "strong_candidate":
        return "strong"
    return "usable_with_review"


def _do_not_present_reason(workload: WorkloadAssessment) -> str | None:
    blockers = set(workload.blocking_flags)
    if "CONFLICTED" in blockers:
        return "Identity evidence conflicts across source exports."
    if "DUPLICATE_CANDIDATES" in blockers:
        return "Multiple possible workload matches must be resolved first."
    if "NO_BACKUP_MATCH" in blockers:
        return "Backup evidence is missing, so protection and change-rate claims are not defensible."
    if "MISSING_STORAGE_USED" in blockers:
        return "Used-storage evidence is missing, so footprint ratios cannot be trusted."
    return None


def business_impact_for(workload: WorkloadAssessment) -> BusinessImpact:
    motion = workload.winning_motion.motion
    presentation_class = presentation_class_for(workload)
    blockers = set(workload.blocking_flags)
    missing_priority = _highest_missing_priority(workload.missing_evidence)

    next_step = MOTION_NEXT_STEP[motion]
    question = MOTION_QUESTION[motion]
    if presentation_class == "do_not_present":
        next_step = "Resolve the blocking evidence issue before presenting this workload as an opportunity."
        question = _do_not_present_reason(workload) or "What source evidence must be corrected before this workload is reviewed?"
    elif presentation_class == "needs_more_data":
        next_step = "Request the missing evidence before using this workload as a lead candidate."
        if workload.missing_evidence:
            question = FIELD_QUESTIONS.get(workload.missing_evidence[0].field, workload.missing_evidence[0].reason)
    elif "SNAPSHOT_PRESENT" in blockers:
        next_step = "Review snapshot ownership and age before putting this workload in a customer-facing queue."
        question = "Is the snapshot intentional, temporary, or evidence of an unmanaged protection process?"
    elif "NAME_MATCH_ONLY" in blockers:
        next_step = "Confirm the workload identity match before relying on this result."
        question = "Can the source exports provide a shared workload UUID or approved identity override?"

    return BusinessImpact(
        presentation_class=presentation_class,
        owner_persona=OWNER_PERSONA[motion],
        recommended_next_step=next_step,
        business_question=question,
        why_this_matters=MOTION_IMPACT[motion],
        evidence_strength=evidence_strength_for(workload),
        missing_evidence_priority=missing_priority,
        do_not_present_reason=_do_not_present_reason(workload),
        motion_fit_explanation="; ".join(workload.winning_motion.reason_text),
    )


def workflow_summary(assessment: AssessmentResult) -> dict:
    presentation_counts = Counter(
        business_impact_for(workload).presentation_class for workload in assessment.workloads
    )
    motion_counts = Counter(workload.winning_motion.motion for workload in assessment.workloads)
    high_priority_missing = Counter(
        request.field
        for workload in assessment.workloads
        for request in workload.missing_evidence
        if request.priority == "high"
        and request.field not in DERIVED_MISSING_EVIDENCE_FIELDS
    )
    blockers = Counter(
        flag for workload in assessment.workloads for flag in workload.blocking_flags
    )
    return {
        "workloads_assessed": len(assessment.workloads),
        "motion_counts": {motion: motion_counts.get(motion, 0) for motion in MOTION_LABELS},
        "presentation_counts": {
            "strong_candidate": presentation_counts.get("strong_candidate", 0),
            "review_candidate": presentation_counts.get("review_candidate", 0),
            "needs_more_data": presentation_counts.get("needs_more_data", 0),
            "do_not_present": presentation_counts.get("do_not_present", 0),
        },
        "top_missing_evidence": [
            {"field": field, "affected_workloads": count}
            for field, count in sorted(
                high_priority_missing.items(),
                key=lambda item: (-item[1], item[0]),
            )[:10]
        ],
        "top_blockers": [
            {"flag": flag, "affected_workloads": count}
            for flag, count in sorted(blockers.items(), key=lambda item: (-item[1], item[0]))[:10]
        ],
    }
