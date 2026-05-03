"""Human-readable reports, checklists, questions, and evidence bundles."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import zipfile

import yaml

from .assessment import build_preflight_assessment
from .candidates import prerequisite_identity
from .models import Finding, ObservedPrerequisite, OwnerWorkItem, PreflightAssessment, Summary
from .normalize import compact_join, stable_hash
from .redact import redact_outputs
from .report import (
    FINDINGS_COLUMNS,
    OBSERVED_COLUMNS,
    OWNER_WORKLIST_COLUMNS,
    finding_to_row,
    observed_to_row,
    owner_work_item_to_row,
    write_findings_csv,
    write_observed_csv,
    write_summary_json,
)
from .support_files import owner_label_for_category


CHECKLIST_COLUMNS = ["category", "prerequisite", "status", "evidence", "owner", "decision", "notes"]


def write_markdown_report(path: str | Path, findings: list[Finding], summary: Summary, *, owner_map: list[object] | None = None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    assessment = build_preflight_assessment(findings=findings, summary=summary, owner_map=owner_map or [])
    decision_status_by_id = {item.prerequisite_id: item.status for item in assessment.decisions}
    lines = [
        "# Recovery Preflight Assessment",
        "",
        f"Assessment decision: **{assessment.decision}**",
        f"Recovery set: `{summary.recovery_set}`",
        "",
        assessment.business_impact,
        "",
        "DNS logs show lookups, not actual connections. Inventory absence means absent from the supplied CSV.",
        "",
        "## Executive Result",
        "",
    ]
    for item in assessment.executive_summary:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Recovery-Scope Gaps By Service Family",
            "",
        ]
    )
    if not assessment.service_families:
        lines.append("No prerequisite candidates were found in the supplied evidence.")
    for family in assessment.service_families:
        if family.status == "PASS" and not family.missing_count and not family.review_count:
            continue
        lines.extend(
            [
                f"### {family.display_name}: {family.status}",
                "",
                f"- Impact: {family.impact_summary}",
                f"- Missing: {family.missing_count}; review: {family.review_count}; accepted risk: {family.accepted_risk_count}; present: {family.present_count}",
                f"- Owners: {compact_join(family.owner_teams) or 'unassigned'}",
                "",
            ]
        )
        for decision in [item for item in assessment.decisions if item.prerequisite_id in family.decisions and item.status in {"missing", "review", "accepted_risk"}]:
            lines.extend(
                [
                    f"- `{decision.status}` {decision.display_name}: {decision.recommended_action}",
                    f"  Evidence: {decision.evidence_strength}; observed queries: {decision.observed_query_count}; owner: {decision.owner_team or 'unassigned'}",
                ]
            )
        lines.append("")
    lines.extend(
        [
            "## Owner Routing",
            "",
        ]
    )
    if not assessment.owner_work_items:
        lines.append("No owner-routed work items were produced.")
    else:
        by_owner: dict[str, list[object]] = {}
        for item in assessment.owner_work_items:
            by_owner.setdefault(item.owner_team or "unassigned", []).append(item)
        for owner, items in sorted(by_owner.items()):
            lines.append(f"### {owner}")
            for item in items:
                contact = f" ({item.owner_contact})" if item.owner_contact else ""
                lines.append(f"- {item.severity} {item.prerequisite}{contact}: {item.human_question}")
            lines.append("")
    lines.extend(
        [
            "## Evidence Quality",
            "",
            f"- Status: {summary.evidence_quality.get('status', 'UNKNOWN')}",
        ]
    )
    for issue in summary.evidence_quality.get("issues", []):
        lines.append(f"- {issue}")
    metrics = summary.evidence_quality.get("metrics", {})
    if metrics:
        lines.extend(["", "### Evidence Metrics", ""])
        for key, value in metrics.items():
            lines.append(f"- {key}: {value}")
    if assessment.evidence_improvement_actions:
        lines.extend(["", "### Evidence Improvement Actions", ""])
        for action in assessment.evidence_improvement_actions:
            lines.append(f"- {action.priority}: {action.action} Reason: {action.reason}")
    input_audit = summary.evidence_quality.get("input_audit", {})
    if input_audit:
        lines.extend(["", "### Input Audit", ""])
        for key in (
            "stale_inventory_rows",
            "duplicate_fqdn_count",
            "duplicate_ip_count",
            "conflicting_alias_count",
            "missing_owner_team_rows",
            "missing_business_service_rows",
            "missing_criticality_rows",
            "missing_recovery_tier_rows",
            "missing_site_rows",
            "missing_environment_rows",
        ):
            lines.append(f"- {key}: {input_audit.get(key, 0)}")
    if summary.window_comparison:
        lines.extend(["", "## Window Comparison", ""])
        for item in summary.window_comparison:
            lines.append(
                f"- {item.get('window_hours')}h: {item.get('lint_status')} with {item.get('dns_log_rows_in_window')} DNS rows; new missing: {compact_join(item.get('new_missing_prerequisites', [])) or 'none'}"
            )
    metadata = summary.run_metadata.get("recovery_set_metadata", {})
    if metadata:
        lines.extend(["", "## Recovery Set Context", ""])
        for key in ("purpose", "site", "notes"):
            if metadata.get(key):
                lines.append(f"- {key}: {metadata[key]}")
    business_context = summary.run_metadata.get("business_context", {})
    if business_context:
        lines.extend(["", "## Business Context", ""])
        _append_count_lines(lines, "Protected systems by owner team", business_context.get("protected_systems_by_owner_team", {}))
        _append_count_lines(lines, "Protected systems by business service", business_context.get("protected_systems_by_business_service", {}))
        _append_count_lines(lines, "Protected systems by criticality", business_context.get("protected_systems_by_criticality", {}))
        _append_count_lines(lines, "Protected systems by recovery tier", business_context.get("protected_systems_by_recovery_tier", {}))
        _append_count_lines(lines, "Protected systems by site", business_context.get("protected_systems_by_site", {}))
        _append_count_lines(lines, "Protected systems by environment", business_context.get("protected_systems_by_environment", {}))
        _append_count_lines(lines, "Impacted examples by owner team", business_context.get("impacted_examples_by_owner_team", {}))
        _append_count_lines(lines, "Impacted examples by business service", business_context.get("impacted_examples_by_business_service", {}))
        _append_count_lines(lines, "Impacted examples by criticality", business_context.get("impacted_examples_by_criticality", {}))
        _append_count_lines(lines, "Impacted examples by recovery tier", business_context.get("impacted_examples_by_recovery_tier", {}))
        _append_count_lines(lines, "Impacted examples by site", business_context.get("impacted_examples_by_site", {}))
        _append_count_lines(lines, "Impacted examples by environment", business_context.get("impacted_examples_by_environment", {}))
    lines.extend(["", "## Detailed Audit Appendix", ""])
    for finding in findings:
        lines.extend(
            [
                f"### {finding.severity}: {finding.prerequisite_name}",
                "",
                f"- Category: `{finding.category}`",
                f"- Confidence: `{finding.confidence}`",
                f"- Status: `{decision_status_by_id.get(prerequisite_identity(finding), 'audit')}`",
                f"- Target: `{finding.prerequisite_target or finding.prerequisite_target_ip}`",
                f"- Observed query count: {finding.observed_query_count}",
                f"- Owner: {owner_label_for_category(owner_map or [], finding.category) or 'unassigned'}",
                f"- Reason codes: `{compact_join(finding.reason_codes)}`",
                f"- Question: {finding.suggested_human_question}",
                "",
            ]
        )
    lines.extend(["## Recommended Questions", ""])
    for question in summary.recommended_next_questions:
        lines.append(f"- {question}")
    lines.extend(["", "## Limitations", ""])
    for limitation in assessment.limitations:
        lines.append(f"- {limitation}")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_questions(path: str | Path, findings: list[Finding], *, owner_map: list[object] | None = None, include_info: bool = False) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    by_audience = {
        "recovery team": [],
        "DNS/resolver team": [],
        "directory-service team": [],
        "application owner": [],
        "storage/file-services team": [],
        "database team": [],
        "remote-access team": [],
        "time-service team": [],
        "license/service owner": [],
    }
    for finding in findings:
        if finding.present_in_recovery_set:
            continue
        if finding.severity == "INFO" and not include_info:
            continue
        owner_label = owner_label_for_category(owner_map or [], finding.category)
        if owner_label:
            by_audience.setdefault(owner_label, []).append(finding.suggested_human_question)
            continue
        audience = "application owner"
        if finding.category == "dns_resolver":
            audience = "DNS/resolver team"
        elif finding.category in {"directory_service", "kerberos_service", "global_catalog"}:
            audience = "directory-service team"
        elif finding.category == "file_share":
            audience = "storage/file-services team"
        elif finding.category == "database_host":
            audience = "database team"
        elif finding.category == "vpn_endpoint":
            audience = "remote-access team"
        elif finding.category == "time_service":
            audience = "time-service team"
        elif finding.category == "license_server":
            audience = "license/service owner"
        by_audience[audience].append(finding.suggested_human_question)
    lines = ["# Recovery-Test Preflight Questions", ""]
    for audience, questions in by_audience.items():
        if not questions:
            continue
        lines.extend([f"## {audience.title()}", ""])
        for question in sorted(set(questions)):
            lines.append(f"- {question}")
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_checklist(path: str | Path, observed: list[ObservedPrerequisite], *, owner_map: list[object] | None = None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    deduped = _dedupe_observed_for_checklist(observed)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHECKLIST_COLUMNS)
        writer.writeheader()
        for item in deduped:
            if item.present_in_recovery_set:
                status = "present"
            elif "ACCEPTED_RISK_APPLIED" in item.reason_codes:
                status = "accepted_risk"
            elif "OPTIONAL_PREREQ_OBSERVED" in item.reason_codes:
                status = "optional"
            elif "NO_RECOVERY_SET_MATCH" in item.reason_codes:
                status = "absent_from_recovery_set"
            else:
                status = "review"
            writer.writerow(
                {
                    "category": item.category,
                    "prerequisite": item.prerequisite_name,
                    "status": status,
                    "evidence": compact_join(item.reason_codes),
                    "owner": owner_label_for_category(owner_map or [], item.category),
                    "decision": "",
                    "notes": "",
                }
            )


def _dedupe_observed_for_checklist(observed: list[ObservedPrerequisite]) -> list[ObservedPrerequisite]:
    grouped: dict[tuple[str, str], ObservedPrerequisite] = {}
    for item in observed:
        key = _observed_key(item)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = item.model_copy(deep=True)
            continue
        existing.observed_query_count += item.observed_query_count
        existing.observed_by_protected_systems = max(existing.observed_by_protected_systems, item.observed_by_protected_systems)
        existing.reason_codes = _unique(existing.reason_codes + item.reason_codes)
        existing.present_in_recovery_set = existing.present_in_recovery_set or item.present_in_recovery_set
    return sorted(grouped.values(), key=lambda item: (item.category, item.prerequisite_name))


def _observed_key(item: ObservedPrerequisite) -> tuple[str, str]:
    for value in [item.prerequisite_target_ip] + item.example_answer_ips:
        if value:
            return (item.category, f"ip:{value}")
    for value in [item.prerequisite_target, item.prerequisite_name] + item.example_answer_names:
        if value:
            return (item.category, value.lower())
    return (item.category, item.prerequisite_name.lower())


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _append_count_lines(lines: list[str], title: str, counts: dict[str, int]) -> None:
    if not counts:
        return
    lines.append(f"- {title}: {compact_join([f'{key}={value}' for key, value in list(counts.items())[:5]])}")


def bundle_evidence(
    *,
    findings: list[Finding],
    observed: list[ObservedPrerequisite],
    summary: Summary,
    output: str | Path,
    redact: bool = False,
    config: dict[str, object] | None = None,
    input_paths: list[str | Path] | None = None,
    assessment: PreflightAssessment | None = None,
    owner_work_items: list[OwnerWorkItem] | None = None,
) -> None:
    if redact:
        findings, observed, summary = redact_outputs(findings, observed, summary)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprints = {
        str(path): stable_hash(Path(path).read_bytes().hex())
        for path in (input_paths or [])
        if Path(path).exists()
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("findings.csv", _csv_text(FINDINGS_COLUMNS, [finding_to_row(item) for item in findings]))
        archive.writestr("observed_prereqs.csv", _csv_text(OBSERVED_COLUMNS, [observed_to_row(item) for item in observed]))
        archive.writestr("summary.json", json.dumps(summary.model_dump(), indent=2) + "\n")
        if assessment is not None:
            archive.writestr("preflight_assessment.json", json.dumps(assessment.model_dump(mode="json"), indent=2) + "\n")
        if owner_work_items is not None:
            archive.writestr("owner_worklist.csv", _csv_text(OWNER_WORKLIST_COLUMNS, [owner_work_item_to_row(item) for item in owner_work_items]))
        archive.writestr("warnings.json", json.dumps(summary.warnings, indent=2) + "\n")
        archive.writestr("config.yml", yaml.safe_dump(config or {}, sort_keys=False))
        archive.writestr("input_fingerprints.json", json.dumps(fingerprints, indent=2, sort_keys=True) + "\n")
        questions = "\n".join(f"- {question}" for question in summary.recommended_next_questions)
        archive.writestr("handoff_questions.md", "# Handoff Questions\n\n" + questions + "\n")


def load_findings_csv(path: str | Path) -> list[Finding]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [_finding_from_row(row) for row in csv.DictReader(handle)]


def load_observed_csv(path: str | Path) -> list[ObservedPrerequisite]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return [_observed_from_row(row) for row in csv.DictReader(handle)]


def load_summary_json(path: str | Path) -> Summary:
    return Summary.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def _csv_text(fieldnames: list[str], rows: list[dict[str, object]]) -> str:
    from io import StringIO

    handle = StringIO()
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def _finding_from_row(row: dict[str, str]) -> Finding:
    return Finding(
        severity=row["severity"],  # type: ignore[arg-type]
        confidence=row["confidence"],  # type: ignore[arg-type]
        finding_code=row["finding_code"],
        category=row["category"],
        prerequisite_name=row["prerequisite_name"],
        prerequisite_target=row["prerequisite_target"],
        prerequisite_target_ip=row["prerequisite_target_ip"],
        recovery_set=row["recovery_set"],
        present_in_recovery_set=row["present_in_recovery_set"].lower() == "true",
        match_basis=row["match_basis"],
        observed_query_count=int(row["observed_query_count"] or 0),
        observed_by_protected_systems=int(row["observed_by_protected_systems"] or 0),
        example_protected_systems=_split(row["example_protected_systems"]),
        example_qnames=_split(row["example_qnames"]),
        example_answer_names=_split(row["example_answer_names"]),
        example_answer_ips=_split(row["example_answer_ips"]),
        evidence_source=row["evidence_source"],
        reason_codes=_split(row["reason_codes"]),
        suggested_action=row["suggested_action"],
        suggested_human_question=row["suggested_human_question"],
        missing_data=_split(row["missing_data"]),
        source_rows=_split(row["source_rows"]),
    )


def _observed_from_row(row: dict[str, str]) -> ObservedPrerequisite:
    return ObservedPrerequisite(
        category=row["category"],
        prerequisite_name=row["prerequisite_name"],
        prerequisite_target=row["prerequisite_target"],
        prerequisite_target_ip=row["prerequisite_target_ip"],
        confidence=row["confidence"],  # type: ignore[arg-type]
        present_in_recovery_set=row["present_in_recovery_set"].lower() == "true",
        match_basis=row["match_basis"],
        observed_query_count=int(row["observed_query_count"] or 0),
        observed_by_protected_systems=int(row["observed_by_protected_systems"] or 0),
        evidence_source=row["evidence_source"],
        reason_codes=_split(row["reason_codes"]),
        notes=_split(row["notes"]),
    )


def _split(value: str) -> list[str]:
    return [part for part in value.split("|") if part]
