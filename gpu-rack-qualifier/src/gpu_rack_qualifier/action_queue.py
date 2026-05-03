from __future__ import annotations

import csv
from pathlib import Path

from .config import ensure_parent
from .models import QualificationResult, ReviewQueueRow
from .quarantine import quarantine_row
from .readiness import business_risk, readiness_lane


REVIEW_QUEUE_COLUMNS = [
    "priority",
    "node_name",
    "readiness_lane",
    "recommended_state",
    "primary_reason",
    "operator_action",
    "business_risk",
    "confidence",
    "blocking_evidence",
    "next_question",
    "source_evidence",
]


def review_queue_rows(results: list[QualificationResult]) -> list[ReviewQueueRow]:
    rows = []
    for result in sorted(results, key=lambda item: item.features.node_name):
        if result.qualification_status == "PASS":
            continue
        qrow = quarantine_row(result)
        rows.append(
            ReviewQueueRow(
                priority=_priority(result),
                node_name=result.features.node_name,
                readiness_lane=readiness_lane(result),
                recommended_state=result.recommended_state,
                primary_reason=qrow.primary_reason,
                operator_action=qrow.operator_action,
                business_risk=business_risk(result),
                confidence=result.features.confidence,
                blocking_evidence=";".join(result.features.blockers or result.features.warnings or [qrow.primary_reason]),
                next_question=result.features.suggested_operator_question or "",
                source_evidence=";".join(result.features.source_evidence),
            )
        )
    return sorted(rows, key=lambda row: (row.priority, row.node_name))


def review_queue_counts(results: list[QualificationResult]) -> dict[str, int]:
    rows = review_queue_rows(results)
    counts = {"total": len(rows), "P0": 0, "P1": 0, "P2": 0}
    for row in rows:
        counts[row.priority] = counts.get(row.priority, 0) + 1
    return counts


def write_review_queue_csv(path: Path, results: list[QualificationResult]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_QUEUE_COLUMNS)
        writer.writeheader()
        for row in review_queue_rows(results):
            writer.writerow(_model_dict(row))


def _priority(result: QualificationResult) -> str:
    if result.qualification_status == "QUARANTINE":
        return "P0"
    if result.qualification_status == "AVOID_MULTINODE":
        return "P1"
    return "P2"


def _model_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
