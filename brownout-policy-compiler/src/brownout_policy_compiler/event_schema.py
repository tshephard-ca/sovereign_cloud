from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .models import Confidence, DdosEvent, ValidationResult


def load_event(path: str | Path) -> DdosEvent:
    data = json.loads(Path(path).read_text())
    return DdosEvent.model_validate(data)


def try_load_event(path: str | Path) -> tuple[DdosEvent | None, ValidationResult]:
    result = ValidationResult()
    try:
        return load_event(path), result
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        result.blockers.append("EVENT_INVALID")
        result.warnings.append(str(exc))
        return None, result


def validate_event(event: DdosEvent, strict: bool = False) -> ValidationResult:
    result = ValidationResult()
    if not event.targets:
        result.blockers.append("NO_VALID_TARGETS")
    if event.confidence == Confidence.LOW:
        result.warnings.append("EVENT_CONFIDENCE_LOW")
        if strict:
            result.blockers.append("EVENT_CONFIDENCE_LOW")
    for target in event.targets:
        if target.ports is None:
            result.warnings.append("EVENT_TARGET_PORTS_MISSING")
            if strict:
                result.blockers.append("EVENT_TARGET_PORTS_MISSING")
        if target.observed_bps is None and target.observed_pps is None:
            result.warnings.append("EVENT_METRICS_MISSING")
        if target.baseline_bps is None and target.baseline_pps is None:
            result.warnings.append("EVENT_BASELINE_MISSING")
    if event.signals.top_source_prefixes:
        result.warnings.append("SOURCE_PREFIXES_ADVISORY_ONLY")
        if not event.signals.telemetry_source or event.signals.sampling_window_seconds is None or event.signals.evidence_age_seconds is None:
            result.warnings.append("EVENT_SIGNAL_EVIDENCE_METADATA_MISSING")
            if strict:
                result.blockers.append("EVENT_SIGNAL_EVIDENCE_METADATA_MISSING")
    if event.signals.spoofing_likely and event.signals.top_source_prefixes:
        result.warnings.append("SPOOFING_LIKELY_SOURCE_BLOCKS_SKIPPED")
    return dedupe_validation(result)


def dedupe_validation(result: ValidationResult) -> ValidationResult:
    result.warnings = sorted(set(result.warnings))
    result.blockers = sorted(set(result.blockers))
    return result
