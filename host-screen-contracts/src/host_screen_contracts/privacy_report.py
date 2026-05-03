from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .field_classification import find_field
from .field_map import FieldMap, FieldMapEntry
from .models import screen_ref_for_seq
from .redact import REDACTED, is_sensitive_name, should_redact
from .trace_schema import ActionEvent, ScreenEvent, TraceEvent


@dataclass(frozen=True)
class PrivacyFinding:
    kind: str
    screen_ref: str | None
    field_id: str | None
    row: int | None
    col: int | None
    name: str | None
    reason: str
    severity: str
    redacted: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "screen_ref": self.screen_ref,
            "field_id": self.field_id,
            "row": self.row,
            "col": self.col,
            "name": self.name,
            "reason": self.reason,
            "severity": self.severity,
            "redacted": self.redacted,
        }


def _is_value_redacted(value: str) -> bool:
    return value == REDACTED or value.startswith("<REDACTED") or value == ""


LIKELY_SENSITIVE_TEXT_RE = re.compile(r"\b\d{8,}\b|[A-Z]{2,}[A-Z0-9]*\d{6,}[A-Z0-9]*")


def _sensitive_reason(name: str | None, entry: FieldMapEntry | None, *, hidden: bool = False) -> str | None:
    if entry and entry.sensitive is False and not hidden:
        return None
    if hidden and not (entry and entry.sensitive is False):
        return "hidden_field"
    if should_redact(name, entry, redact=True):
        return "field_marked_or_named_sensitive"
    return None


def _severity(reason: str, name: str | None = None, entry: FieldMapEntry | None = None) -> str:
    if reason == "hidden_field":
        return "HIGH"
    if entry and entry.sensitive is True:
        return "HIGH"
    if is_sensitive_name(name):
        return "HIGH"
    if reason == "raw_text_sensitive_pattern":
        return "MEDIUM"
    return "MEDIUM"


def _non_sensitive_spans(screen: ScreenEvent, screen_ref: str, field_map: FieldMap) -> dict[int, list[tuple[int, int]]]:
    spans: dict[int, list[tuple[int, int]]] = {}
    for field in screen.fields:
        entry = field_map.find_for_field(screen_ref, field)
        if entry and entry.sensitive is False:
            spans.setdefault(field.row, []).append((field.col, field.col + field.length - 1))
    for entry in field_map.entries_for(screen_ref):
        if entry.sensitive is False and entry.row is not None and entry.col is not None and entry.length is not None:
            spans.setdefault(entry.row, []).append((entry.col, entry.col + entry.length - 1))
    return spans


def _overlaps(spans: list[tuple[int, int]], start_col: int, end_col: int) -> bool:
    return any(start_col <= end and end_col >= start for start, end in spans)


def generate_privacy_report(events: list[TraceEvent], field_map: FieldMap | None = None) -> dict[str, Any]:
    field_map = field_map or FieldMap()
    findings: list[PrivacyFinding] = []
    latest_screen: tuple[str, ScreenEvent] | None = None

    for event in events:
        if isinstance(event, ScreenEvent):
            screen_ref = screen_ref_for_seq(event.seq)
            latest_screen = (screen_ref, event)
            non_sensitive_spans = _non_sensitive_spans(event, screen_ref, field_map)
            for field in event.fields:
                entry = field_map.find_for_field(screen_ref, field)
                name = entry.name if entry and entry.name else field.id
                reason = _sensitive_reason(name, entry, hidden=field.hidden)
                if reason and field.value:
                    findings.append(
                        PrivacyFinding(
                            kind="screen_field_value",
                            screen_ref=screen_ref,
                            field_id=field.id,
                            row=field.row,
                            col=field.col,
                            name=name,
                            reason=reason,
                            severity=_severity(reason, name, entry),
                            redacted=_is_value_redacted(field.value),
                        )
                    )
            for row_number, row_text in enumerate(event.text, start=1):
                for match in LIKELY_SENSITIVE_TEXT_RE.finditer(row_text):
                    value = match.group(0)
                    if value == REDACTED or value.startswith("REDACTED"):
                        continue
                    if _overlaps(non_sensitive_spans.get(row_number, []), match.start() + 1, match.end()):
                        continue
                    findings.append(
                        PrivacyFinding(
                            kind="screen_text_pattern",
                            screen_ref=screen_ref,
                            field_id=None,
                            row=row_number,
                            col=match.start() + 1,
                            name=None,
                            reason="raw_text_sensitive_pattern",
                            severity="MEDIUM",
                            redacted=False,
                        )
                    )
        elif isinstance(event, ActionEvent) and latest_screen:
            screen_ref, screen = latest_screen
            for action_input in event.inputs:
                field = find_field(
                    screen_ref,
                    screen,
                    field_map,
                    field_id=action_input.field_id,
                    row=action_input.row,
                    col=action_input.col,
                    fallback_value=action_input.value,
                )
                entry = None
                name = action_input.field_id
                if field is not None:
                    entry = field_map.find_for_field(screen_ref, field)
                    name = entry.name if entry and entry.name else field.id
                reason = _sensitive_reason(name, entry)
                if reason and action_input.value:
                    findings.append(
                        PrivacyFinding(
                            kind="action_input_value",
                            screen_ref=screen_ref,
                            field_id=action_input.field_id or (field.id if field else None),
                            row=action_input.row,
                            col=action_input.col,
                            name=name,
                            reason=reason,
                            severity=_severity(reason, name, entry),
                            redacted=_is_value_redacted(action_input.value),
                        )
                    )

    finding_dicts = [finding.as_dict() for finding in findings]
    unredacted = [finding for finding in finding_dicts if not finding["redacted"]]
    confirmed_sensitive_unredacted = [
        finding
        for finding in unredacted
        if finding["reason"] == "field_marked_or_named_sensitive"
    ]
    potential_identifier_patterns = [
        finding
        for finding in unredacted
        if finding["reason"] == "raw_text_sensitive_pattern"
    ]
    hidden_field_unredacted = [
        finding
        for finding in unredacted
        if finding["reason"] == "hidden_field"
    ]
    severity_counts = _severity_counts(finding_dicts)
    unredacted_severity_counts = _severity_counts(unredacted)
    return {
        "schema_version": "1.0",
        "finding_count": len(finding_dicts),
        "unredacted_sensitive_value_count": len(unredacted),
        "confirmed_sensitive_unredacted_count": len(confirmed_sensitive_unredacted),
        "potential_identifier_pattern_count": len(potential_identifier_patterns),
        "hidden_field_unredacted_count": len(hidden_field_unredacted),
        "finding_severity_counts": severity_counts,
        "unredacted_severity_counts": unredacted_severity_counts,
        "highest_unredacted_severity": _highest_severity(unredacted_severity_counts),
        "findings": finding_dicts,
    }


def _severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for finding in findings:
        severity = finding.get("severity", "MEDIUM")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _highest_severity(counts: dict[str, int]) -> str | None:
    for severity in ("HIGH", "MEDIUM", "LOW"):
        if counts.get(severity, 0):
            return severity
    return None
