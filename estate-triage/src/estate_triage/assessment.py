"""Assessment result assembly, confidence, ranking, and compatibility output."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from estate_triage.config import Thresholds
from estate_triage.evidence import (
    ASSESSMENT_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
    DataQualityFinding,
)
from estate_triage.feature_engine import FeatureSet, compute_features
from estate_triage.identity import IdentityResolutionResult, ResolvedWorkload
from estate_triage.models import Confidence, TriageResult
from estate_triage.policy import (
    DEFAULT_POLICY_PACK,
    MOTION_ORDER,
    MotionAssessment,
    PolicyEvaluation,
    PolicyPack,
    choose_winning_motion,
    evaluate_policy,
)


class RankingMode(str, Enum):
    GLOBAL = "global"
    BALANCED = "balanced"
    PER_MOTION = "per_motion"
    CONFIDENCE_FIRST = "confidence_first"
    BLOCKERS_FIRST = "blockers_first"
    MISSING_EVIDENCE_FIRST = "missing_evidence_first"


class MissingEvidenceRequest(BaseModel):
    field: str
    priority: str = "medium"
    reason: str


class BlockingFlagDetail(BaseModel):
    flag: str
    severity: str
    reason: str


class WorkloadAssessment(BaseModel):
    schema_version: str = ASSESSMENT_SCHEMA_VERSION
    trace_schema_version: str = TRACE_SCHEMA_VERSION
    workload_id: str
    workload_key: str
    workload_name: str
    identity: ResolvedWorkload
    feature_set: FeatureSet
    policy_evaluation: PolicyEvaluation
    winning_motion: MotionAssessment
    confidence: Confidence
    confidence_factors: dict[str, str] = Field(default_factory=dict)
    blocking_flags: list[str] = Field(default_factory=list)
    blocking_flag_details: list[BlockingFlagDetail] = Field(default_factory=list)
    missing_evidence: list[MissingEvidenceRequest] = Field(default_factory=list)
    data_quality: list[DataQualityFinding] = Field(default_factory=list)


class AssessmentResult(BaseModel):
    schema_version: str = ASSESSMENT_SCHEMA_VERSION
    trace_schema_version: str = TRACE_SCHEMA_VERSION
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    policy_id: str
    policy_version: str
    workloads: list[WorkloadAssessment]
    input: dict[str, int]
    data_quality: list[DataQualityFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def _add_once(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _blocking_flags(workload: ResolvedWorkload, features: FeatureSet, winner: MotionAssessment) -> list[str]:
    flags = list(winner.blocking_flags)
    if workload.backup is None:
        _add_once(flags, "NO_BACKUP_MATCH")
    if features.value("snapshot_present"):
        _add_once(flags, "SNAPSHOT_PRESENT")
    if workload.inventory.in_use_mib is None or workload.inventory.in_use_mib <= 0:
        _add_once(flags, "MISSING_STORAGE_USED")
    if workload.backup is None or workload.backup.backup_total_mib is None:
        _add_once(flags, "MISSING_BACKUP_SIZE")
    if features.value("change_rate_pct") is None:
        _add_once(flags, "MISSING_CHANGE_RATE")
    if workload.matched_by == "NAME":
        _add_once(flags, "NAME_MATCH_ONLY")
    if workload.status in {"CONFLICTED", "DUPLICATE_CANDIDATES"}:
        _add_once(flags, workload.status)
    if winner.motion == "RIGHTSIZING_REVIEW" and winner.allocation_only_rightsizing:
        _add_once(flags, "LOW_CONFIDENCE_RIGHTSIZING")
    if winner.motion == "MIGRATION_REVIEW" and features.value("powered_off"):
        _add_once(flags, "POWERED_OFF_NOT_MIGRATION_CANDIDATE")
    return flags


def _has_enough_metrics(workload: ResolvedWorkload, features: FeatureSet, winner: MotionAssessment) -> bool:
    if winner.motion == "MIGRATION_REVIEW":
        return (
            workload.backup is not None
            and features.value("has_recent_backup") is True
            and features.value("change_rate_pct") is not None
            and workload.inventory.in_use_mib is not None
            and workload.inventory.os is not None
        )
    if winner.motion == "ARCHIVE_REVIEW":
        return workload.inventory.power_state is not None or features.value("stale_backup") is True
    if winner.motion == "RIGHTSIZING_REVIEW":
        if winner.allocation_only_rightsizing:
            return False
        return (
            workload.inventory.cpu_usage_pct is not None
            or workload.inventory.memory_usage_pct is not None
            or features.value("cpu_p95_pct") is not None
            or features.value("memory_p95_pct") is not None
        )
    if winner.motion == "DR_TIER_REVIEW":
        return (
            workload.backup is not None
            and workload.backup.backup_total_mib is not None
            and workload.inventory.in_use_mib is not None
            and features.value("change_rate_pct") is not None
        )
    return False


def _confidence(workload: ResolvedWorkload, features: FeatureSet, winner: MotionAssessment) -> Confidence:
    if workload.backup is None:
        return "low"
    if workload.status in {"CONFLICTED", "DUPLICATE_CANDIDATES"}:
        return "low"
    if winner.motion == "RIGHTSIZING_REVIEW" and winner.allocation_only_rightsizing:
        return "low"
    if not _has_enough_metrics(workload, features, winner):
        return "low"
    if workload.matched_by == "UUID":
        return "high"
    if workload.matched_by == "NAME":
        return "medium"
    return "low"


def _missing_requests(features: FeatureSet) -> list[MissingEvidenceRequest]:
    high_priority = {
        "uuid",
        "backup_total_mib",
        "in_use_mib",
        "avg_daily_change_mib",
        "latest_restore_point_utc",
        "cpu_usage_pct",
        "memory_usage_pct",
        "cpu_p95_pct",
        "memory_p95_pct",
    }
    return [
        MissingEvidenceRequest(
            field=field,
            priority="high" if field in high_priority else "medium",
            reason="Additional evidence would improve confidence or enable feature calculation.",
        )
        for field in features.missing_evidence
    ]


def _confidence_factors(
    workload: ResolvedWorkload,
    features: FeatureSet,
    winner: MotionAssessment,
) -> dict[str, str]:
    return {
        "identity": workload.trace.confidence,
        "metrics": "sufficient" if _has_enough_metrics(workload, features, winner) else "insufficient",
        "right_sizing": "allocation_only" if winner.allocation_only_rightsizing else "evidence_backed",
        "data_quality": str(features.value("data_quality_risk") or "unknown"),
    }


def _blocking_flag_details(flags: list[str]) -> list[BlockingFlagDetail]:
    severity = {
        "NO_BACKUP_MATCH": ("high", "Backup evidence is missing for this workload."),
        "SNAPSHOT_PRESENT": ("medium", "Snapshot footprint should be reviewed before action."),
        "MISSING_STORAGE_USED": ("high", "Storage-used evidence is required for storage ratios."),
        "MISSING_BACKUP_SIZE": ("high", "Backup size is required for backup-footprint rules."),
        "MISSING_CHANGE_RATE": ("medium", "Change-rate evidence improves confidence."),
        "NAME_MATCH_ONLY": ("medium", "Name-only identity match needs review."),
        "CONFLICTED": ("high", "Identity evidence has a conflict."),
        "DUPLICATE_CANDIDATES": ("high", "Multiple identity candidates require review."),
        "LOW_CONFIDENCE_RIGHTSIZING": ("medium", "Right-sizing signal is allocation-only."),
        "POWERED_OFF_NOT_MIGRATION_CANDIDATE": ("medium", "Powered-off state weakens migration-review fit."),
        "SPARSE_UTILIZATION_WINDOW": ("medium", "Utilization sample window is sparse."),
    }
    return [
        BlockingFlagDetail(
            flag=flag,
            severity=severity.get(flag, ("low", "Review before presenting."))[0],
            reason=severity.get(flag, ("low", "Review before presenting."))[1],
        )
        for flag in flags
    ]


def assess_workload(
    workload: ResolvedWorkload,
    thresholds: Thresholds,
    *,
    policy_pack: PolicyPack = DEFAULT_POLICY_PACK,
    now: datetime | None = None,
) -> WorkloadAssessment:
    features = compute_features(workload, thresholds, now=now)
    policy_evaluation = evaluate_policy(workload, features, thresholds, policy_pack=policy_pack)
    winner = choose_winning_motion(policy_evaluation)
    confidence = _confidence(workload, features, winner)
    blocking_flags = _blocking_flags(workload, features, winner)
    return WorkloadAssessment(
        workload_id=workload.workload_id,
        workload_key=features.value("workload_key"),
        workload_name=workload.inventory.name,
        identity=workload,
        feature_set=features,
        policy_evaluation=policy_evaluation,
        winning_motion=winner,
        confidence=confidence,
        confidence_factors=_confidence_factors(workload, features, winner),
        blocking_flags=blocking_flags,
        blocking_flag_details=_blocking_flag_details(blocking_flags),
        missing_evidence=_missing_requests(features),
        data_quality=[
            *workload.inventory_record.data_quality,
            *(workload.backup_record.data_quality if workload.backup_record else []),
            *workload.data_quality,
        ],
    )


def assemble_assessment(
    identity_result: IdentityResolutionResult,
    thresholds: Thresholds,
    *,
    policy_pack: PolicyPack = DEFAULT_POLICY_PACK,
    now: datetime | None = None,
    warnings: list[str] | None = None,
) -> AssessmentResult:
    workloads = [
        assess_workload(workload, thresholds, policy_pack=policy_pack, now=now)
        for workload in identity_result.workloads
    ]
    return AssessmentResult(
        policy_id=policy_pack.id,
        policy_version=policy_pack.version,
        workloads=workloads,
        input={
            "inventory_rows": identity_result.inventory_rows,
            "backup_rows": identity_result.backup_rows,
            "utilization_rows": identity_result.utilization_rows,
            "matched_by_uuid": identity_result.matched_by_uuid,
            "matched_by_name": identity_result.matched_by_name,
            "unmatched_inventory": identity_result.unmatched_inventory,
            "conflicted": identity_result.conflicted,
            "duplicate_candidates": identity_result.duplicate_candidates,
        },
        data_quality=identity_result.data_quality,
        warnings=[*(warnings or []), *identity_result.warnings],
    )


def _to_triage_result(assessment: WorkloadAssessment) -> TriageResult:
    workload = assessment.identity
    backup = workload.backup
    inventory = workload.inventory
    features = assessment.feature_set
    winner = assessment.winning_motion
    return TriageResult(
        workload_key=assessment.workload_key,
        workload_name=assessment.workload_name,
        matched_by=workload.matched_by,
        primary_motion=winner.motion,
        opportunity_score=winner.score,
        confidence=assessment.confidence,
        reason_codes=winner.reason_codes,
        reason_text="; ".join(winner.reason_text),
        blocking_flags=assessment.blocking_flags,
        missing_data=[request.field for request in assessment.missing_evidence],
        power_state=inventory.power_state,
        cpu_count=inventory.cpu_count,
        memory_mib=inventory.memory_mib,
        provisioned_mib=inventory.provisioned_mib,
        in_use_mib=inventory.in_use_mib,
        os=inventory.os,
        latest_restore_point_utc=backup.latest_restore_point_utc if backup else None,
        restore_point_count=backup.restore_point_count if backup else None,
        backup_total_mib=backup.backup_total_mib if backup else None,
        avg_daily_change_mib=backup.avg_daily_change_mib if backup else None,
        change_rate_pct=features.value("change_rate_pct"),
        backup_to_used_ratio=features.value("backup_to_used_ratio"),
        source_inventory_row=inventory.source_row,
        source_backup_row=backup.source_row if backup else None,
    )


def rank_assessments(
    assessment: AssessmentResult,
    *,
    top_n: int,
    mode: RankingMode = RankingMode.BALANCED,
) -> list[TriageResult]:
    results = [_to_triage_result(workload) for workload in assessment.workloads]

    def global_key(result: TriageResult):
        return (
            -result.opportunity_score,
            MOTION_ORDER[result.primary_motion],
            result.workload_key,
            result.source_inventory_row,
        )

    def balanced_key(result: TriageResult):
        if result.confidence == "high" and not result.blocking_flags:
            presentation_rank = 0
        elif result.confidence == "high":
            presentation_rank = 1
        elif result.confidence == "medium":
            presentation_rank = 2
        else:
            presentation_rank = 3
        return (
            presentation_rank,
            -result.opportunity_score,
            MOTION_ORDER[result.primary_motion],
            result.workload_key,
            result.source_inventory_row,
        )

    if mode == RankingMode.BALANCED:
        buckets = {
            motion: sorted(
                [result for result in results if result.primary_motion == motion],
                key=balanced_key,
            )
            for motion in MOTION_ORDER
        }
        ranked = []
        index = 0
        while len(ranked) < top_n:
            added = False
            for motion in MOTION_ORDER:
                bucket = buckets[motion]
                if index < len(bucket):
                    ranked.append(bucket[index])
                    added = True
                    if len(ranked) >= top_n:
                        break
            if not added:
                break
            index += 1
    elif mode == RankingMode.PER_MOTION:
        ranked: list[TriageResult] = []
        for motion in MOTION_ORDER:
            motion_rows = sorted(
                [result for result in results if result.primary_motion == motion],
                key=global_key,
            )[:top_n]
            ranked.extend(motion_rows)
    elif mode == RankingMode.CONFIDENCE_FIRST:
        ranked = sorted(
            results,
            key=lambda result: (
                CONFIDENCE_ORDER[result.confidence],
                -result.opportunity_score,
                MOTION_ORDER[result.primary_motion],
                result.workload_key,
            ),
        )[:top_n]
    elif mode == RankingMode.BLOCKERS_FIRST:
        ranked = sorted(
            results,
            key=lambda result: (
                0 if result.blocking_flags else 1,
                -len(result.blocking_flags),
                -result.opportunity_score,
                result.workload_key,
            ),
        )[:top_n]
    elif mode == RankingMode.MISSING_EVIDENCE_FIRST:
        ranked = sorted(
            results,
            key=lambda result: (
                0 if result.missing_data else 1,
                -len(result.missing_data),
                -result.opportunity_score,
                result.workload_key,
            ),
        )[:top_n]
    else:
        ranked = sorted(results, key=global_key)[:top_n]

    for rank, result in enumerate(ranked, start=1):
        result.rank = rank
    return ranked
