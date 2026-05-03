"""CSV and JSON report writers."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import Finding, ObservedPrerequisite, OwnerWorkItem, PreflightAssessment, Summary
from .normalize import compact_join


FINDINGS_COLUMNS = [
    "severity",
    "confidence",
    "finding_code",
    "category",
    "prerequisite_name",
    "prerequisite_target",
    "prerequisite_target_ip",
    "recovery_set",
    "present_in_recovery_set",
    "match_basis",
    "observed_query_count",
    "observed_by_protected_systems",
    "example_protected_systems",
    "example_qnames",
    "example_answer_names",
    "example_answer_ips",
    "evidence_source",
    "reason_codes",
    "suggested_action",
    "suggested_human_question",
    "missing_data",
    "source_rows",
]


OBSERVED_COLUMNS = [
    "category",
    "prerequisite_name",
    "prerequisite_target",
    "prerequisite_target_ip",
    "confidence",
    "present_in_recovery_set",
    "match_basis",
    "observed_query_count",
    "observed_by_protected_systems",
    "evidence_source",
    "reason_codes",
    "notes",
]


OWNER_WORKLIST_COLUMNS = [
    "owner_team",
    "owner_contact",
    "service_family",
    "category",
    "prerequisite_id",
    "prerequisite",
    "status",
    "impact",
    "severity",
    "evidence_strength",
    "observed_query_count",
    "observed_by_count",
    "recommended_action",
    "human_question",
    "reason_codes",
]


def write_findings_csv(path: str | Path, findings: Iterable[Finding], *, max_examples: int = 5, max_source_rows: int = 20) -> None:
    _ensure_parent(path)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FINDINGS_COLUMNS)
        writer.writeheader()
        for finding in findings:
            writer.writerow(finding_to_row(finding, max_examples=max_examples, max_source_rows=max_source_rows))


def write_observed_csv(path: str | Path, observed: Iterable[ObservedPrerequisite]) -> None:
    _ensure_parent(path)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OBSERVED_COLUMNS)
        writer.writeheader()
        for item in observed:
            writer.writerow(observed_to_row(item))


def write_summary_json(path: str | Path, summary: Summary) -> None:
    _ensure_parent(path)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(summary.model_dump(), handle, indent=2, sort_keys=False)
        handle.write("\n")


def write_preflight_assessment_json(path: str | Path, assessment: PreflightAssessment) -> None:
    _ensure_parent(path)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(assessment.model_dump(mode="json"), handle, indent=2, sort_keys=False)
        handle.write("\n")


def write_owner_worklist_csv(path: str | Path, work_items: Iterable[OwnerWorkItem]) -> None:
    _ensure_parent(path)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OWNER_WORKLIST_COLUMNS)
        writer.writeheader()
        for item in work_items:
            writer.writerow(owner_work_item_to_row(item))


def finding_to_row(finding: Finding, *, max_examples: int = 5, max_source_rows: int = 20) -> dict[str, object]:
    return {
        "severity": finding.severity,
        "confidence": finding.confidence,
        "finding_code": finding.finding_code,
        "category": finding.category,
        "prerequisite_name": finding.prerequisite_name,
        "prerequisite_target": finding.prerequisite_target,
        "prerequisite_target_ip": finding.prerequisite_target_ip,
        "recovery_set": finding.recovery_set,
        "present_in_recovery_set": _bool(finding.present_in_recovery_set),
        "match_basis": finding.match_basis,
        "observed_query_count": finding.observed_query_count,
        "observed_by_protected_systems": finding.observed_by_protected_systems,
        "example_protected_systems": compact_join(finding.example_protected_systems, limit=max_examples),
        "example_qnames": compact_join(finding.example_qnames, limit=max_examples),
        "example_answer_names": compact_join(finding.example_answer_names, limit=max_examples),
        "example_answer_ips": compact_join(finding.example_answer_ips, limit=max_examples),
        "evidence_source": finding.evidence_source,
        "reason_codes": compact_join(finding.reason_codes),
        "suggested_action": finding.suggested_action,
        "suggested_human_question": finding.suggested_human_question,
        "missing_data": compact_join(finding.missing_data),
        "source_rows": compact_join(finding.source_rows, limit=max_source_rows),
    }


def observed_to_row(item: ObservedPrerequisite) -> dict[str, object]:
    return {
        "category": item.category,
        "prerequisite_name": item.prerequisite_name,
        "prerequisite_target": item.prerequisite_target,
        "prerequisite_target_ip": item.prerequisite_target_ip,
        "confidence": item.confidence,
        "present_in_recovery_set": _bool(item.present_in_recovery_set),
        "match_basis": item.match_basis,
        "observed_query_count": item.observed_query_count,
        "observed_by_protected_systems": item.observed_by_protected_systems,
        "evidence_source": item.evidence_source,
        "reason_codes": compact_join(item.reason_codes),
        "notes": compact_join(item.notes),
    }


def owner_work_item_to_row(item: OwnerWorkItem) -> dict[str, object]:
    return {
        "owner_team": item.owner_team,
        "owner_contact": item.owner_contact,
        "service_family": item.service_family,
        "category": item.category,
        "prerequisite_id": item.prerequisite_id,
        "prerequisite": item.prerequisite,
        "status": item.status,
        "impact": item.impact,
        "severity": item.severity,
        "evidence_strength": item.evidence_strength,
        "observed_query_count": item.observed_query_count,
        "observed_by_count": item.observed_by_count,
        "recommended_action": item.recommended_action,
        "human_question": item.human_question,
        "reason_codes": compact_join(item.reason_codes),
    }


def _ensure_parent(path: str | Path) -> None:
    parent = Path(path).parent
    if str(parent) and str(parent) != ".":
        parent.mkdir(parents=True, exist_ok=True)


def _bool(value: bool) -> str:
    return "true" if value else "false"
