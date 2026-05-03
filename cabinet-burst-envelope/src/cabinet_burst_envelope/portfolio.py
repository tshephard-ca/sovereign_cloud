from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .remediation import REMEDIATION_RULES, remediation_categories
from .report import ensure_parent, write_json


PORTFOLIO_COLUMNS = [
    "cabinet_id",
    "case_dir",
    "review_lane",
    "envelope_status",
    "confidence",
    "evidence_quality_score",
    "recommended_sustained_kw",
    "recommended_short_burst_kw",
    "limiting_factor",
    "primary_constraint",
    "business_action",
    "electrical_risk",
    "thermal_risk",
    "trip_risk",
    "aligned_coverage_pct",
    "remediation_categories",
    "warnings",
    "blockers",
    "reason_codes",
]


def find_cabinet_cases(input_root: str | Path) -> list[Path]:
    root = Path(input_root)
    candidates: list[Path] = []
    for path in sorted(root.rglob("cabinet_profile.yml")):
        case_dir = path.parent
        if (case_dir / "pdu_power.csv").exists() and (case_dir / "inlet_temps.csv").exists():
            candidates.append(case_dir)
    return candidates


def portfolio_row(case_dir: Path, envelope: Any) -> dict[str, Any]:
    coverage = envelope.evidence_quality.get("coverage", {})
    categories = remediation_categories(envelope.reason_codes, envelope.warnings, envelope.blockers, envelope.missing_data)
    review_lane = envelope.review_lane or {}
    return {
        "cabinet_id": envelope.cabinet_id,
        "case_dir": str(case_dir),
        "review_lane": review_lane.get("lane"),
        "envelope_status": envelope.envelope_status,
        "confidence": envelope.confidence,
        "evidence_quality_score": envelope.evidence_quality.get("score"),
        "recommended_sustained_kw": envelope.recommended_sustained_kw,
        "recommended_short_burst_kw": envelope.recommended_short_burst_kw,
        "limiting_factor": envelope.limiting_factor,
        "primary_constraint": review_lane.get("primary_constraint"),
        "business_action": review_lane.get("business_action"),
        "electrical_risk": envelope.electrical.get("electrical_risk"),
        "thermal_risk": envelope.thermal.get("thermal_risk"),
        "trip_risk": envelope.electrical.get("trip_risk"),
        "aligned_coverage_pct": coverage.get("aligned_coverage_pct"),
        "remediation_categories": ";".join(categories),
        "warnings": ";".join(envelope.warnings),
        "blockers": ";".join(envelope.blockers),
        "reason_codes": ";".join(envelope.reason_codes),
    }


def write_portfolio_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    output = ensure_parent(path)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PORTFOLIO_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in PORTFOLIO_COLUMNS})


def portfolio_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    remediation: dict[str, list[str]] = {category: [] for category in sorted(REMEDIATION_RULES)}
    for row in rows:
        status = str(row.get("envelope_status", "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1
        for category in str(row.get("remediation_categories", "")).split(";"):
            if category:
                remediation.setdefault(category, []).append(row["cabinet_id"])
    return {
        "schema_version": "cabinet-burst-envelope.portfolio.v1",
        "cabinet_count": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "review_lane_counts": dict(
            sorted(
                {
                    lane: len([row for row in rows if row.get("review_lane") == lane])
                    for lane in {str(row.get("review_lane")) for row in rows if row.get("review_lane")}
                }.items()
            )
        ),
        "cabinets_ready_for_review": [row["cabinet_id"] for row in rows if row.get("envelope_status") == "READY_FOR_REVIEW"],
        "cabinets_needing_review": [row["cabinet_id"] for row in rows if row.get("envelope_status") == "REVIEW_REQUIRED"],
        "cabinets_do_not_expand": [row["cabinet_id"] for row in rows if row.get("envelope_status") == "DO_NOT_EXPAND"],
        "cabinets_insufficient_data": [row["cabinet_id"] for row in rows if row.get("envelope_status") == "INSUFFICIENT_DATA"],
        "remediation_groups": {category: cabinets for category, cabinets in remediation.items() if cabinets},
        "rows": rows,
    }


def write_portfolio_json(path: str | Path, rows: list[dict[str, Any]]) -> None:
    write_json(path, portfolio_summary(rows))
