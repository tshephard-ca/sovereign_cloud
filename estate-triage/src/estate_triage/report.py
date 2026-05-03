"""CSV and JSON report writers."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from estate_triage.assessment import AssessmentResult
from estate_triage.models import TriageResult
from estate_triage.privacy import PrivacyMode, redact_assessment


OUTPUT_COLUMNS = [
    "rank",
    "workload_key",
    "workload_name",
    "matched_by",
    "primary_motion",
    "opportunity_score",
    "confidence",
    "reason_codes",
    "reason_text",
    "blocking_flags",
    "missing_data",
    "power_state",
    "cpu_count",
    "memory_mib",
    "provisioned_mib",
    "in_use_mib",
    "os",
    "latest_restore_point_utc",
    "restore_point_count",
    "backup_total_mib",
    "avg_daily_change_mib",
    "change_rate_pct",
    "backup_to_used_ratio",
    "source_inventory_row",
    "source_backup_row",
]


class Redactor:
    def __init__(self) -> None:
        self._names: dict[str, str] = {}

    def name(self, original: str) -> str:
        key = original or ""
        if key not in self._names:
            self._names[key] = f"workload_{len(self._names) + 1:03d}"
        return self._names[key]

    def key(self, original: str) -> str:
        return hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def result_to_row(result: TriageResult, *, redactor: Redactor | None = None) -> dict[str, str]:
    workload_key = result.workload_key
    workload_name = result.workload_name
    if redactor is not None:
        workload_key = redactor.key(workload_key)
        workload_name = redactor.name(workload_name)

    return {
        "rank": str(result.rank),
        "workload_key": workload_key,
        "workload_name": workload_name,
        "matched_by": result.matched_by,
        "primary_motion": result.primary_motion,
        "opportunity_score": str(result.opportunity_score),
        "confidence": result.confidence,
        "reason_codes": "|".join(result.reason_codes),
        "reason_text": result.reason_text,
        "blocking_flags": "|".join(result.blocking_flags),
        "missing_data": "|".join(result.missing_data),
        "power_state": result.power_state or "",
        "cpu_count": _format_number(result.cpu_count),
        "memory_mib": _format_number(result.memory_mib),
        "provisioned_mib": _format_number(result.provisioned_mib),
        "in_use_mib": _format_number(result.in_use_mib),
        "os": result.os or "",
        "latest_restore_point_utc": _format_datetime(result.latest_restore_point_utc),
        "restore_point_count": _format_number(result.restore_point_count),
        "backup_total_mib": _format_number(result.backup_total_mib),
        "avg_daily_change_mib": _format_number(result.avg_daily_change_mib),
        "change_rate_pct": _format_number(result.change_rate_pct),
        "backup_to_used_ratio": _format_number(result.backup_to_used_ratio),
        "source_inventory_row": str(result.source_inventory_row),
        "source_backup_row": "" if result.source_backup_row is None else str(result.source_backup_row),
    }


def write_results_csv(path: Path, results: list[TriageResult], *, redact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    redactor = Redactor() if redact else None
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(result_to_row(result, redactor=redactor))


def write_summary_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_assessment_json(
    path: Path,
    assessment: AssessmentResult,
    *,
    redact: bool = False,
    salt: str = "",
    privacy_mode: PrivacyMode = "minimal",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = redact_assessment(assessment, salt=salt, mode=privacy_mode) if redact else assessment
    path.write_text(
        json.dumps(output.model_dump(mode="json"), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
