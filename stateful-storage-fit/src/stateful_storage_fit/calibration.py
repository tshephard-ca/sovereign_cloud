from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import FitResult


CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _lower_confidence(current: str, ceiling: str) -> str:
    if CONFIDENCE_ORDER.get(current, 0) > CONFIDENCE_ORDER.get(ceiling, 0):
        return ceiling
    return current


def load_calibration_report(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def apply_calibration(result: FitResult, calibration: dict[str, Any] | None) -> FitResult:
    if not calibration:
        return result

    readiness = calibration.get("readiness", {})
    readiness_level = readiness.get("level", "UNKNOWN")
    status_metrics = calibration.get("outcome_metrics", {}).get("by_predicted_status", {})
    current_status_metrics = status_metrics.get(result.fit_status, {})
    case_count = int(current_status_metrics.get("case_count", 0) or 0)
    storage_failure_rate = current_status_metrics.get("storage_failure_rate")

    calibration_summary = {
        "readiness_level": readiness_level,
        "readiness_blockers": readiness.get("blockers", []),
        "status_sample_count": case_count,
        "status_storage_failure_rate": storage_failure_rate,
    }
    if result.analysis is not None:
        result.analysis["calibration"] = calibration_summary

    if readiness_level in {"RESEARCH_ONLY", "UNKNOWN"}:
        if "CALIBRATION_RESEARCH_ONLY" not in result.warnings:
            result.warnings.append("CALIBRATION_RESEARCH_ONLY")
        result.confidence = _lower_confidence(result.confidence, "MEDIUM")

    minimum_status_samples = int(readiness.get("minimum_status_samples", 5) or 5)
    if case_count < minimum_status_samples:
        if "CALIBRATION_LOW_SAMPLE_FOR_STATUS" not in result.warnings:
            result.warnings.append("CALIBRATION_LOW_SAMPLE_FOR_STATUS")
        result.confidence = _lower_confidence(result.confidence, "MEDIUM")

    if result.fit_status == "PASS" and isinstance(storage_failure_rate, (int, float)):
        if storage_failure_rate >= 0.25:
            if "CALIBRATION_PASS_FAILURE_RATE_HIGH" not in result.warnings:
                result.warnings.append("CALIBRATION_PASS_FAILURE_RATE_HIGH")
            result.confidence = _lower_confidence(result.confidence, "LOW")
        elif storage_failure_rate >= 0.10:
            if "CALIBRATION_PASS_FAILURE_RATE_ELEVATED" not in result.warnings:
                result.warnings.append("CALIBRATION_PASS_FAILURE_RATE_ELEVATED")
            result.confidence = _lower_confidence(result.confidence, "MEDIUM")

    return result

