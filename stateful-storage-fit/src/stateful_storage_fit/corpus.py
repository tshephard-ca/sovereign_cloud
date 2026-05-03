from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .engine import analyze_paths
from .origins import is_generated_origin

SUCCESS_OUTCOMES = {
    "onboarded_successfully",
    "storage_fit_confirmed",
}

STORAGE_FAILURE_OUTCOMES = {
    "blocked_by_storage",
    "failed_storage_assumption",
    "storage_rework_required",
}

NEUTRAL_OUTCOMES = {
    "not_attempted",
    "unknown",
    "blocked_by_non_storage",
}

VALID_FIT_STATUSES = {"PASS", "REVIEW", "FAIL"}
VALID_OUTCOME_STATUSES = SUCCESS_OUTCOMES | STORAGE_FAILURE_OUTCOMES | NEUTRAL_OUTCOMES


def _business_impact(case: dict) -> list[dict[str, Any]]:
    impact = case.get("business_impact") or []
    return impact if isinstance(impact, list) else []


def _resolve(base: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def _load_cases(corpus_dir: Path) -> list[tuple[Path, dict]]:
    cases: list[tuple[Path, dict]] = []
    for path in sorted(corpus_dir.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            cases.append((path, data))
    return cases


def _case_id(case_path: Path, case: dict) -> str:
    return str(case.get("id") or case_path.stem)


def _expert_reviews(case: dict) -> list[dict[str, Any]]:
    reviews = case.get("expert_reviews") or []
    return reviews if isinstance(reviews, list) else []


def _outcomes(case: dict) -> list[dict[str, Any]]:
    outcomes = case.get("outcomes") or []
    return outcomes if isinstance(outcomes, list) else []


def _review_decisions(case: dict) -> list[str]:
    values = []
    for review in _expert_reviews(case):
        decision = review.get("fit_status") or review.get("decision")
        if decision:
            values.append(str(decision))
    return values


def _consensus(values: list[str]) -> str | None:
    if not values:
        return None
    counts = Counter(values)
    value, count = counts.most_common(1)[0]
    return value if count == len(values) else None


def _expected_status(case: dict) -> tuple[str | None, str]:
    adjudicated = case.get("adjudicated_fit_status")
    if adjudicated:
        return str(adjudicated), "adjudicated"
    consensus = _consensus(_review_decisions(case))
    if consensus:
        return consensus, "expert_consensus"
    expected = case.get("expected_fit_status")
    if expected:
        return str(expected), str(case.get("label_source") or "expected_label")
    return None, "missing"


def _outcome_statuses(case: dict) -> list[str]:
    values: list[str] = []
    for outcome in _outcomes(case):
        status = outcome.get("status")
        if status:
            values.append(str(status))
    return values


def _has_storage_failure_outcome(case: dict) -> bool:
    return any(status in STORAGE_FAILURE_OUTCOMES for status in _outcome_statuses(case))


def _has_success_outcome(case: dict) -> bool:
    return any(status in SUCCESS_OUTCOMES for status in _outcome_statuses(case))


def _case_quality(case: dict) -> dict[str, Any]:
    reviews = _expert_reviews(case)
    outcomes = _outcomes(case)
    review_consensus = _consensus(_review_decisions(case))
    decisive_outcome_count = sum(
        1 for status in _outcome_statuses(case) if status in SUCCESS_OUTCOMES or status in STORAGE_FAILURE_OUTCOMES
    )
    has_outcome = decisive_outcome_count > 0
    explicit_source = case.get("label_source") or case.get("case_kind")
    if has_outcome:
        label_source = "outcome_linked"
    elif review_consensus:
        label_source = "expert_consensus"
    elif reviews:
        label_source = "expert_reviewed_no_consensus"
    else:
        label_source = str(explicit_source or "synthetic")
    data_origin = str(case.get("data_origin", "unknown"))
    synthetic_origin = is_generated_origin(data_origin) or case.get("case_kind") == "synthetic" or case.get("label_source") == "synthetic"
    trusted = label_source in {"outcome_linked", "expert_consensus", "adjudicated"} and not synthetic_origin
    return {
        "label_source": label_source,
        "data_origin": data_origin,
        "synthetic_origin": synthetic_origin,
        "trusted": trusted,
        "expert_review_count": len(reviews),
        "expert_review_consensus": review_consensus,
        "outcome_count": len(outcomes),
        "decisive_outcome_count": decisive_outcome_count,
        "outcome_statuses": _outcome_statuses(case),
        "has_storage_failure_outcome": _has_storage_failure_outcome(case),
        "has_success_outcome": _has_success_outcome(case),
    }


def _case_contract_issues(case: dict) -> list[str]:
    issues: list[str] = []
    if not case.get("id"):
        issues.append("FIELD_MISSING:id")
    for field in ["data_origin", "profile_origin", "storage_profile"]:
        if not case.get(field):
            issues.append(f"FIELD_MISSING:{field}")
    decision = case.get("engine_decision")
    if not isinstance(decision, dict) or decision.get("fit_status") not in VALID_FIT_STATUSES:
        issues.append("ENGINE_DECISION_INVALID_OR_MISSING_FIT_STATUS")
    for review in _expert_reviews(case):
        if review.get("fit_status") not in VALID_FIT_STATUSES:
            issues.append("EXPERT_REVIEW_INVALID_FIT_STATUS")
    for outcome in _outcomes(case):
        status = outcome.get("status")
        if status and status not in VALID_OUTCOME_STATUSES:
            issues.append(f"OUTCOME_INVALID_STATUS:{status}")
    return issues


def _outcome_alignment(actual_status: str, case: dict) -> str:
    if _has_storage_failure_outcome(case):
        if actual_status == "PASS":
            return "false_pass_storage_failure"
        if actual_status == "FAIL":
            return "fail_confirmed_by_storage_outcome"
        return "review_storage_failure"
    if _has_success_outcome(case):
        if actual_status == "FAIL":
            return "false_fail_successful_outcome"
        if actual_status == "PASS":
            return "pass_confirmed_by_successful_outcome"
        return "review_successful_outcome"
    return "no_decisive_outcome"


def _readiness(
    *,
    case_count: int,
    trusted_count: int,
    outcome_count: int,
    pass_failure_rate: float | None,
    min_outcome_cases: int,
    min_outcome_coverage: float,
    max_pass_storage_failure_rate: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    outcome_coverage = outcome_count / case_count if case_count else 0.0
    trusted_coverage = trusted_count / case_count if case_count else 0.0
    if outcome_count < min_outcome_cases:
        blockers.append("INSUFFICIENT_OUTCOME_LINKED_CASES")
    if outcome_coverage < min_outcome_coverage:
        blockers.append("INSUFFICIENT_OUTCOME_COVERAGE")
    if trusted_coverage < 0.5:
        blockers.append("INSUFFICIENT_TRUSTED_LABEL_COVERAGE")
    if pass_failure_rate is not None and pass_failure_rate > max_pass_storage_failure_rate:
        blockers.append("PASS_STORAGE_FAILURE_RATE_TOO_HIGH")

    if blockers:
        level = "RESEARCH_ONLY"
    elif outcome_count >= 100 and outcome_coverage >= 0.6 and (pass_failure_rate or 0.0) <= max_pass_storage_failure_rate / 2:
        level = "PRODUCTION_READY"
    else:
        level = "CALIBRATED_INTERNAL"
    return {
        "level": level,
        "blockers": blockers,
        "case_count": case_count,
        "trusted_label_count": trusted_count,
        "trusted_label_coverage": trusted_coverage,
        "outcome_linked_case_count": outcome_count,
        "outcome_coverage": outcome_coverage,
        "minimum_outcome_cases": min_outcome_cases,
        "minimum_outcome_coverage": min_outcome_coverage,
        "maximum_pass_storage_failure_rate": max_pass_storage_failure_rate,
        "minimum_status_samples": 5,
    }


def _status_outcome_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for status in ["PASS", "REVIEW", "FAIL"]:
        selected = [
            row
            for row in rows
            if row["actual_fit_status"] == status
            and row["quality"]["decisive_outcome_count"]
            and row["quality"]["contract_valid"]
        ]
        storage_failures = sum(1 for row in selected if row["quality"]["has_storage_failure_outcome"])
        successes = sum(1 for row in selected if row["quality"]["has_success_outcome"])
        count = len(selected)
        metrics[status] = {
            "case_count": count,
            "storage_failure_count": storage_failures,
            "success_count": successes,
            "storage_failure_rate": storage_failures / count if count else None,
            "success_rate": successes / count if count else None,
        }
    return metrics


def _reason_code_outcome_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_code: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not row["quality"]["decisive_outcome_count"] or not row["quality"]["contract_valid"]:
            continue
        for code in row["reason_codes"]:
            by_code.setdefault(code, []).append(row)
    metrics = {}
    for code, selected in sorted(by_code.items()):
        storage_failures = sum(1 for row in selected if row["quality"]["has_storage_failure_outcome"])
        successes = sum(1 for row in selected if row["quality"]["has_success_outcome"])
        count = len(selected)
        metrics[code] = {
            "case_count": count,
            "storage_failure_count": storage_failures,
            "success_count": successes,
            "storage_failure_rate": storage_failures / count if count else None,
            "success_rate": successes / count if count else None,
        }
    return metrics


def evaluate_corpus(
    corpus_dir: Path,
    *,
    min_outcome_cases: int = 20,
    min_outcome_coverage: float = 0.30,
    max_pass_storage_failure_rate: float = 0.10,
) -> dict:
    cases = _load_cases(corpus_dir)
    status_counts: Counter[str] = Counter()
    expected_counts: Counter[str] = Counter()
    label_source_counts: Counter[str] = Counter()
    outcome_alignment_counts: Counter[str] = Counter()
    matches = 0
    labeled_count = 0
    mismatches = []
    requirement_matches: Counter[str] = Counter()
    requirement_totals: Counter[str] = Counter()
    trusted_count = 0
    outcome_count = 0
    rows: list[dict[str, Any]] = []
    impact_records: list[dict[str, Any]] = []
    for case_path, case in cases:
        base = case_path.parent
        bundle = analyze_paths(
            df=_resolve(base, case.get("df")),
            mount=_resolve(base, case.get("mount")),
            fstab=_resolve(base, case.get("fstab")),
            iostat=_resolve(base, case.get("iostat")),
            ps=_resolve(base, case.get("ps")),
            storage_profile_path=_resolve(base, case.get("storage_profile")),
            config=_resolve(base, case.get("config")),
            policy_pack_path=_resolve(base, case.get("policy_pack")),
            data_paths=case.get("data_paths") or [],
            strict=False,
        )
        result = bundle.result
        expected_status, expected_source = _expected_status(case)
        quality = _case_quality(case)
        contract_issues = _case_contract_issues(case)
        quality["contract_valid"] = not contract_issues
        quality["contract_issues"] = contract_issues
        if contract_issues:
            quality["trusted"] = False
        label_source_counts[quality["label_source"]] += 1
        if quality["trusted"]:
            trusted_count += 1
        if quality["decisive_outcome_count"] and quality["contract_valid"]:
            outcome_count += 1
        status_counts[result.fit_status] += 1
        if expected_status is not None:
            labeled_count += 1
            expected_counts[str(expected_status)] += 1
        alignment = _outcome_alignment(result.fit_status, case)
        outcome_alignment_counts[alignment] += 1
        if expected_status is not None and result.fit_status == expected_status:
            matches += 1
        elif expected_status is not None:
            mismatches.append(
                {
                    "case": _case_id(case_path, case),
                    "expected_fit_status": expected_status,
                    "expected_source": expected_source,
                    "actual_fit_status": result.fit_status,
                    "reason_codes": result.reason_codes,
                    "blockers": result.blockers,
                    "outcome_alignment": alignment,
                }
            )
        expected_requirements = case.get("expected_requirements") or {}
        for field, expected in expected_requirements.items():
            requirement_totals[field] += 1
            actual = getattr(result, field, None)
            if actual == expected:
                requirement_matches[field] += 1
        rows.append(
            {
                "case": _case_id(case_path, case),
                "expected_fit_status": expected_status,
                "expected_source": expected_source,
                "actual_fit_status": result.fit_status,
                "confidence": result.confidence,
                "reason_codes": result.reason_codes,
                "blockers": result.blockers,
                "quality": quality,
                "outcome_alignment": alignment,
                "lifecycle_state": case.get("lifecycle_state"),
            }
        )
        impact_records.extend(_business_impact(case))
    total = len(cases)
    requirement_accuracy = {
        field: requirement_matches[field] / count if count else 0.0
        for field, count in sorted(requirement_totals.items())
    }
    status_outcome_metrics = _status_outcome_metrics(rows)
    pass_failure_rate = status_outcome_metrics.get("PASS", {}).get("storage_failure_rate")
    readiness = _readiness(
        case_count=total,
        trusted_count=trusted_count,
        outcome_count=outcome_count,
        pass_failure_rate=pass_failure_rate,
        min_outcome_cases=min_outcome_cases,
        min_outcome_coverage=min_outcome_coverage,
        max_pass_storage_failure_rate=max_pass_storage_failure_rate,
    )
    return {
        "schema_version": "1.0",
        "case_count": total,
        "labeled_case_count": labeled_count,
        "decision_accuracy": matches / labeled_count if labeled_count else None,
        "trusted_label_count": trusted_count,
        "outcome_linked_case_count": outcome_count,
        "label_source_counts": dict(sorted(label_source_counts.items())),
        "actual_status_counts": dict(sorted(status_counts.items())),
        "expected_status_counts": dict(sorted(expected_counts.items())),
        "requirement_accuracy": requirement_accuracy,
        "outcome_alignment_counts": dict(sorted(outcome_alignment_counts.items())),
        "outcome_metrics": {
            "by_predicted_status": status_outcome_metrics,
            "by_reason_code": _reason_code_outcome_metrics(rows),
        },
        "business_impact_metrics": _business_impact_metrics(impact_records),
        "readiness": readiness,
        "cases": rows,
        "mismatches": mismatches,
        "note": "Synthetic labels measure rule regression only. Production confidence requires expert-reviewed and outcome-linked cases that pass readiness gates.",
    }


def _business_impact_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    def sum_int(field: str) -> int:
        return sum(int(record.get(field) or 0) for record in records)

    def count_true(field: str) -> int:
        return sum(1 for record in records if record.get(field) is True)

    decisions: Counter[str] = Counter()
    for record in records:
        decision = record.get("decision")
        if decision:
            decisions[str(decision)] += 1
    return {
        "record_count": len(records),
        "assessment_minutes_total": sum_int("assessment_minutes"),
        "expert_review_minutes_total": sum_int("expert_review_minutes"),
        "blockers_found_before_pilot_count": count_true("blocker_found_before_pilot"),
        "failed_pilots_avoided_count": count_true("failed_pilot_avoided"),
        "platform_gaps_identified_count": count_true("platform_gap_identified"),
        "decision_counts": dict(sorted(decisions.items())),
    }


def case_template(case_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": case_id,
        "case_kind": "created",
        "data_origin": "real_workload",
        "profile_origin": "user_supplied",
        "lifecycle_state": "created",
        "label_source": "untrusted_template",
        "bundle": {
            "path": "bundles/workload-001",
            "manifest": "bundles/workload-001/manifest.json",
            "validation": {},
        },
        "df": "vm/df.txt",
        "mount": "vm/mount.txt",
        "fstab": "vm/fstab.txt",
        "iostat": "vm/iostat.txt",
        "ps": "vm/ps.txt",
        "storage_profile": "storage-profile.yml",
        "storage_profile_snapshot": {},
        "engine_decision": {
            "fit_status": "REVIEW",
            "required_access_mode": "ReadWriteOnce",
            "required_volume_mode": "Filesystem",
            "preferred_storage_kind": "block",
            "reason_codes": [],
            "blockers": [],
        },
        "expected_requirements": {},
        "review_template": {
            "reviewer_id": "redacted-reviewer-id",
            "reviewed_at": "YYYY-MM-DD",
            "fit_status": "REVIEW",
            "required_access_mode": "ReadWriteOnce",
            "required_volume_mode": "Filesystem",
            "preferred_storage_kind": "block",
            "blockers": [],
            "confidence": "MEDIUM",
            "notes": "Explain why the reviewer agrees or disagrees with the engine.",
        },
        "expert_reviews": [],
        "adjudication": None,
        "outcome_template": {
            "recorded_at": "YYYY-MM-DD",
            "status": "unknown",
            "target_storage_class": "generic-storage-class-name",
            "observed_storage_blockers": [],
            "notes": "Use onboarded_successfully, storage_fit_confirmed, blocked_by_storage, failed_storage_assumption, storage_rework_required, blocked_by_non_storage, not_attempted, or unknown.",
        },
        "outcomes": [],
        "business_impact_template": {
            "recorded_at": "YYYY-MM-DD",
            "assessment_minutes": 0,
            "expert_review_minutes": 0,
            "blocker_found_before_pilot": False,
            "failed_pilot_avoided": False,
            "platform_gap_identified": False,
            "decision": "proceed | pause | redesign | platform_gap | more_evidence",
        },
        "business_impact": [],
        "reviewer_notes": "Keep proprietary names and secrets out of committed corpus cases.",
    }
