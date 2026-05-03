"""Workflow artifacts derived from structured assessments."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from estate_triage.assessment import AssessmentResult, RankingMode, rank_assessments
from estate_triage.business_impact import (
    FIELD_QUESTIONS,
    MOTION_LABELS,
    business_impact_for,
    service_context,
    workflow_summary,
)
from estate_triage.models import PrimaryMotion


PRESENTATION_ORDER = {
    "strong_candidate": 0,
    "review_candidate": 1,
    "needs_more_data": 2,
    "do_not_present": 3,
}

DERIVED_DATA_REQUEST_FIELDS = {
    "backup_to_used_ratio",
    "change_rate_pct",
    "last_powered_on_age_days",
    "last_seen_age_days",
    "snapshot_to_used_ratio",
    "utilization_window_days",
}


class QueueItem(BaseModel):
    workload_id: str
    workload_key: str
    workload_name: str
    motion: PrimaryMotion
    motion_label: str
    score: int
    confidence: str
    state: str = "new"
    presentation_class: str
    evidence_strength: str
    owner_persona: str
    recommended_next_step: str
    business_question: str
    why_this_matters: str
    motion_fit_explanation: str
    do_not_present_reason: str | None = None
    missing_evidence_priority: str
    reason_codes: list[str]
    blocking_flags: list[str]
    missing_evidence: list[str]
    group: dict[str, str | None] = Field(default_factory=dict)


def work_queues(assessment: AssessmentResult) -> dict[str, list[QueueItem]]:
    queues: dict[str, list[QueueItem]] = {
        "MIGRATION_REVIEW": [],
        "ARCHIVE_REVIEW": [],
        "RIGHTSIZING_REVIEW": [],
        "DR_TIER_REVIEW": [],
    }
    for workload in assessment.workloads:
        impact = business_impact_for(workload)
        context = service_context(workload)
        item = QueueItem(
            workload_id=workload.workload_id,
            workload_key=workload.workload_key,
            workload_name=workload.workload_name,
            motion=workload.winning_motion.motion,
            motion_label=MOTION_LABELS[workload.winning_motion.motion],
            score=workload.winning_motion.score,
            confidence=workload.confidence,
            presentation_class=impact.presentation_class,
            evidence_strength=impact.evidence_strength,
            owner_persona=impact.owner_persona,
            recommended_next_step=impact.recommended_next_step,
            business_question=impact.business_question,
            why_this_matters=impact.why_this_matters,
            motion_fit_explanation=impact.motion_fit_explanation,
            do_not_present_reason=impact.do_not_present_reason,
            missing_evidence_priority=impact.missing_evidence_priority,
            reason_codes=workload.winning_motion.reason_codes,
            blocking_flags=workload.blocking_flags,
            missing_evidence=[request.field for request in workload.missing_evidence],
            group=context,
        )
        queues[item.motion].append(item)
    for motion, items in queues.items():
        queues[motion] = sorted(
            items,
            key=lambda item: (
                PRESENTATION_ORDER[item.presentation_class],
                -item.score,
                item.workload_key,
            ),
        )
    return queues


def evidence_packets(assessment: AssessmentResult) -> list[dict]:
    packets: list[dict] = []
    for workload in sorted(assessment.workloads, key=lambda item: item.workload_key):
        impact = business_impact_for(workload)
        packets.append(
            {
                "workload_id": workload.workload_id,
                "workload_key": workload.workload_key,
                "workload_name": workload.workload_name,
                "motion": workload.winning_motion.motion,
                "motion_label": MOTION_LABELS[workload.winning_motion.motion],
                "confidence": workload.confidence,
                "presentation_class": impact.presentation_class,
                "recommended_next_step": impact.recommended_next_step,
                "business_question": impact.business_question,
                "why_this_matters": impact.why_this_matters,
                "confidence_factors": workload.confidence_factors,
                "identity_summary": workload.identity.trace.field_summary,
                "business_context": service_context(workload),
                "top_features": {
                    name: feature.value
                    for name, feature in sorted(workload.feature_set.features.items())
                    if name
                    in {
                        "backup_to_used_ratio",
                        "change_rate_pct",
                        "provisioned_to_used_ratio",
                        "snapshot_to_used_ratio",
                        "data_quality_risk",
                        "cpu_p95_pct",
                        "memory_p95_pct",
                        "utilization_sample_count",
                    }
                },
                "reason_codes": workload.winning_motion.reason_codes,
                "blocking_flag_details": [
                    detail.model_dump(mode="json") for detail in workload.blocking_flag_details
                ],
                "missing_evidence": [
                    request.model_dump(mode="json") for request in workload.missing_evidence
                ],
            }
        )
    return packets


def data_request_checklist(assessment: AssessmentResult) -> list[dict]:
    grouped: dict[str, dict] = {}
    for workload in assessment.workloads:
        impact = business_impact_for(workload)
        for request in workload.missing_evidence:
            if request.field in DERIVED_DATA_REQUEST_FIELDS:
                continue
            item = grouped.setdefault(
                request.field,
                {
                    "field": request.field,
                    "priority": request.priority,
                    "affected_workloads": 0,
                    "motions": Counter(),
                    "presentation_classes": Counter(),
                    "example_workloads": [],
                    "business_question": FIELD_QUESTIONS.get(request.field, request.reason),
                    "recommended_request": request.reason,
                },
            )
            if request.priority == "high":
                item["priority"] = "high"
            item["affected_workloads"] += 1
            item["motions"][workload.winning_motion.motion] += 1
            item["presentation_classes"][impact.presentation_class] += 1
            if len(item["example_workloads"]) < 5:
                item["example_workloads"].append(workload.workload_key)

    priority_order = {"high": 0, "medium": 1, "low": 2}
    rows = []
    for item in grouped.values():
        rows.append(
            {
                "field": item["field"],
                "priority": item["priority"],
                "affected_workloads": item["affected_workloads"],
                "motions": dict(sorted(item["motions"].items())),
                "presentation_classes": dict(sorted(item["presentation_classes"].items())),
                "example_workloads": item["example_workloads"],
                "business_question": item["business_question"],
                "recommended_request": item["recommended_request"],
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            priority_order.get(str(item["priority"]), 99),
            -int(item["affected_workloads"]),
            str(item["field"]),
        ),
    )


def ranking_mode_comparison(assessment: AssessmentResult, *, top_n: int) -> dict[str, list[str]]:
    return {
        mode.value: [row.workload_key for row in rank_assessments(assessment, top_n=top_n, mode=mode)]
        for mode in RankingMode
    }


def _queue_counts(items: list[QueueItem]) -> dict[str, int]:
    counts = Counter(item.presentation_class for item in items)
    return {
        "strong_candidate": counts.get("strong_candidate", 0),
        "review_candidate": counts.get("review_candidate", 0),
        "needs_more_data": counts.get("needs_more_data", 0),
        "do_not_present": counts.get("do_not_present", 0),
    }


def _top_display(items: list[QueueItem], *, limit: int = 3) -> list[QueueItem]:
    return [
        item
        for item in items
        if item.presentation_class in {"strong_candidate", "review_candidate", "needs_more_data"}
    ][:limit]


def discovery_plan(assessment: AssessmentResult) -> str:
    queues = work_queues(assessment)
    requests = data_request_checklist(assessment)
    lines = [
        "# Discovery Plan",
        "",
        "Use this as a first-meeting plan. It turns the assessment into queues, questions, and missing-data requests; it is not a migration plan or a backup verification.",
        "",
        "## Recommended Meeting Flow",
        "",
        "1. Start with strong candidates to establish where the evidence is usable.",
        "2. Review needs-more-data items as export or owner follow-up, not as opportunities.",
        "3. Keep do-not-present items out of stakeholder recommendations until blockers are resolved.",
        "4. Use the data request checklist to improve the next assessment run.",
        "",
    ]
    for motion, items in queues.items():
        counts = _queue_counts(items)
        lines.append(f"## {MOTION_LABELS[motion]} ({motion})")
        lines.append("")
        lines.append(f"- Total queue: {len(items)}")
        lines.append(f"- Strong candidates: {counts['strong_candidate']}")
        lines.append(f"- Need more data: {counts['needs_more_data']}")
        lines.append(f"- Do not present yet: {counts['do_not_present']}")
        lines.append(f"- Default owner: {items[0].owner_persona if items else 'n/a'}")
        lines.append("")
        for item in _top_display(items):
            lines.append(
                f"- `{item.workload_key}`: {item.recommended_next_step} Question: {item.business_question}"
            )
        if not _top_display(items):
            lines.append("- No presentable candidates in this queue.")
        lines.append("")
    lines.append("## Highest-Value Data Requests")
    lines.append("")
    if requests:
        for item in requests[:5]:
            lines.append(
                f"- `{item['field']}` ({item['priority']}): affects {item['affected_workloads']} workloads. {item['business_question']}"
            )
    else:
        lines.append("- No missing evidence requests were generated.")
    return "\n".join(lines) + "\n"


def executive_summary(assessment: AssessmentResult) -> str:
    queues = work_queues(assessment)
    summary = workflow_summary(assessment)
    data_quality_findings = len(assessment.data_quality) + sum(
        len(workload.data_quality) for workload in assessment.workloads
    )
    lines = [
        "# Executive Summary",
        "",
        "Estate triage turns imperfect infrastructure and backup exports into a local, evidence-backed discovery work plan.",
        "",
        "## Headline",
        "",
        f"- Workloads assessed: {summary['workloads_assessed']}",
        f"- Strong candidates: {summary['presentation_counts']['strong_candidate']}",
        f"- Review candidates: {summary['presentation_counts']['review_candidate']}",
        f"- Need more data: {summary['presentation_counts']['needs_more_data']}",
        f"- Do not present yet: {summary['presentation_counts']['do_not_present']}",
        f"- Data-quality findings: {data_quality_findings}",
        "",
        "## Motion Queues",
        "",
        "| Motion | Total | Strong | Review | Needs data | Do not present |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for motion, items in queues.items():
        counts = _queue_counts(items)
        lines.append(
            f"| {MOTION_LABELS[motion]} | {len(items)} | {counts['strong_candidate']} | {counts['review_candidate']} | {counts['needs_more_data']} | {counts['do_not_present']} |"
        )
    lines.extend(
        [
            "",
            "## Business Impact",
            "",
            "- The output separates credible candidates from rows that need source-data cleanup.",
            "- The workflow pack gives each queue a next step and a human question, so teams can use the result in a discovery call.",
            "- The evidence packet keeps technical traceability available without making the executive summary carry every detail.",
            "",
            "## Caveat",
            "",
            "This is a local triage artifact. It is not a pricing estimate, migration plan, backup verification, or claim that any workload is ready to move.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_work_items_csv(path: Path, queues: dict[str, list[QueueItem]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "state",
                "owner_persona",
                "motion",
                "motion_label",
                "workload_key",
                "workload_name",
                "presentation_class",
                "score",
                "confidence",
                "evidence_strength",
                "recommended_next_step",
                "business_question",
                "why_this_matters",
                "missing_evidence_priority",
                "blocking_flags",
                "missing_evidence",
                "reason_codes",
            ],
        )
        writer.writeheader()
        for motion in queues:
            for item in queues[motion]:
                writer.writerow(
                    {
                        "state": item.state,
                        "owner_persona": item.owner_persona,
                        "motion": item.motion,
                        "motion_label": item.motion_label,
                        "workload_key": item.workload_key,
                        "workload_name": item.workload_name,
                        "presentation_class": item.presentation_class,
                        "score": item.score,
                        "confidence": item.confidence,
                        "evidence_strength": item.evidence_strength,
                        "recommended_next_step": item.recommended_next_step,
                        "business_question": item.business_question,
                        "why_this_matters": item.why_this_matters,
                        "missing_evidence_priority": item.missing_evidence_priority,
                        "blocking_flags": "|".join(item.blocking_flags),
                        "missing_evidence": "|".join(item.missing_evidence),
                        "reason_codes": "|".join(item.reason_codes),
                    }
                )


def _write_data_request_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "field",
                "priority",
                "affected_workloads",
                "motions",
                "presentation_classes",
                "example_workloads",
                "business_question",
                "recommended_request",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "motions": json.dumps(row["motions"], sort_keys=True),
                    "presentation_classes": json.dumps(row["presentation_classes"], sort_keys=True),
                    "example_workloads": "|".join(row["example_workloads"]),
                }
            )


def write_workflow_pack(assessment: AssessmentResult, output_dir: Path, *, top_n: int = 25) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    queues = work_queues(assessment)
    data_requests = data_request_checklist(assessment)
    (output_dir / "work-queues.json").write_text(
        json.dumps(
            {motion: [item.model_dump(mode="json") for item in items] for motion, items in queues.items()},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "business-impact-summary.json").write_text(
        json.dumps(workflow_summary(assessment), indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "evidence-packets.json").write_text(
        json.dumps(evidence_packets(assessment), indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "data-request-checklist.json").write_text(
        json.dumps(data_requests, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "ranking-mode-comparison.json").write_text(
        json.dumps(ranking_mode_comparison(assessment, top_n=top_n), indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "discovery-plan.md").write_text(discovery_plan(assessment), encoding="utf-8")
    (output_dir / "executive-summary.md").write_text(executive_summary(assessment), encoding="utf-8")
    _write_work_items_csv(output_dir / "tasks.csv", queues)
    _write_work_items_csv(output_dir / "business-worklist.csv", queues)
    _write_data_request_csv(output_dir / "data-request-checklist.csv", data_requests)
