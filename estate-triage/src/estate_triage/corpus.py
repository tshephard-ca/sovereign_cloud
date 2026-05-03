"""Sanitized corpus generation and expected-outcome corpus validation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from estate_triage.assessment import AssessmentResult, WorkloadAssessment, assess_workload
from estate_triage.bundle import analyze_bundle
from estate_triage.bundle import load_manifest
from estate_triage.config import Thresholds, load_thresholds
from estate_triage.models import Confidence
from estate_triage.models import PrimaryMotion
from estate_triage.models import TriageError
from estate_triage.policy import load_policy_pack
from estate_triage.privacy import redact_assessment
from estate_triage.report import write_assessment_json


class CorpusWorkloadExpectation(BaseModel):
    workload_key: str
    identity_status: str
    matched_by: str
    primary_motion: PrimaryMotion
    opportunity_score: int
    confidence: Confidence
    reason_codes: list[str]
    blocking_flags: list[str]


class CorpusExpectedOutcomes(BaseModel):
    workload_count: int
    motion_counts: dict[str, int]
    confidence_counts: dict[str, int]
    identity_status_counts: dict[str, int]
    data_quality_codes: dict[str, int]
    workloads: list[CorpusWorkloadExpectation]


class CorpusCase(BaseModel):
    corpus_version: str = "1.0.0"
    source_bundle: str
    expected_summary: dict
    thresholds: dict = Field(default_factory=dict)
    expected_outcomes: CorpusExpectedOutcomes | None = None
    redacted_assessment: str = "assessment.json"
    fingerprints: str = "input-fingerprints.json"


class CorpusCaseValidation(BaseModel):
    case: str
    status: str
    workloads: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CorpusValidation(BaseModel):
    corpus_dir: str
    cases: int
    status: str
    errors: int
    warnings: int
    results: list[CorpusCaseValidation]


def _load_assessment(path: Path) -> AssessmentResult:
    try:
        return AssessmentResult.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TriageError(f"Invalid corpus assessment {path}: {exc}") from exc


def _quality_counts(assessment: AssessmentResult) -> dict[str, int]:
    counter: Counter[str] = Counter(finding.code for finding in assessment.data_quality)
    for workload in assessment.workloads:
        counter.update(finding.code for finding in workload.data_quality)
    return dict(sorted(counter.items()))


def _expectation_for_workload(workload: WorkloadAssessment) -> CorpusWorkloadExpectation:
    return CorpusWorkloadExpectation(
        workload_key=workload.workload_key,
        identity_status=workload.identity.status,
        matched_by=workload.identity.matched_by,
        primary_motion=workload.winning_motion.motion,
        opportunity_score=workload.winning_motion.score,
        confidence=workload.confidence,
        reason_codes=workload.winning_motion.reason_codes,
        blocking_flags=workload.blocking_flags,
    )


def expected_outcomes_from_assessment(assessment: AssessmentResult) -> CorpusExpectedOutcomes:
    return CorpusExpectedOutcomes(
        workload_count=len(assessment.workloads),
        motion_counts=dict(
            sorted(Counter(workload.winning_motion.motion for workload in assessment.workloads).items())
        ),
        confidence_counts=dict(sorted(Counter(workload.confidence for workload in assessment.workloads).items())),
        identity_status_counts=dict(
            sorted(Counter(workload.identity.status for workload in assessment.workloads).items())
        ),
        data_quality_codes=_quality_counts(assessment),
        workloads=[_expectation_for_workload(workload) for workload in assessment.workloads],
    )


def _evaluate_expected_outcomes(
    assessment: AssessmentResult,
    thresholds: Thresholds,
    policy_path: Path,
) -> CorpusExpectedOutcomes:
    policy_pack = load_policy_pack(policy_path)
    evaluated: list[WorkloadAssessment] = []
    for stored in assessment.workloads:
        actual = assess_workload(
            stored.identity,
            thresholds,
            policy_pack=policy_pack,
            now=assessment.created_at_utc,
        )
        # Strict redaction intentionally changes name-only workload keys. Corpus keys
        # are stable redacted identifiers, so keep the stored key for comparison.
        actual.workload_key = stored.workload_key
        evaluated.append(actual)
    actual_assessment = assessment.model_copy(update={"workloads": evaluated})
    return expected_outcomes_from_assessment(actual_assessment)


def _diff_counts(label: str, expected: dict[str, int], actual: dict[str, int]) -> list[str]:
    failures: list[str] = []
    keys = sorted(set(expected) | set(actual))
    for key in keys:
        if expected.get(key, 0) != actual.get(key, 0):
            failures.append(
                f"{label}.{key}: expected {expected.get(key, 0)}, got {actual.get(key, 0)}"
            )
    return failures


def _diff_workloads(
    expected: list[CorpusWorkloadExpectation],
    actual: list[CorpusWorkloadExpectation],
) -> list[str]:
    failures: list[str] = []
    actual_by_key = {item.workload_key: item for item in actual}
    for expected_item in expected:
        actual_item = actual_by_key.get(expected_item.workload_key)
        if actual_item is None:
            failures.append(f"workload.{expected_item.workload_key}: missing from actual outcomes")
            continue
        for field in (
            "identity_status",
            "matched_by",
            "primary_motion",
            "opportunity_score",
            "confidence",
            "reason_codes",
            "blocking_flags",
        ):
            expected_value = getattr(expected_item, field)
            actual_value = getattr(actual_item, field)
            if expected_value != actual_value:
                failures.append(
                    f"workload.{expected_item.workload_key}.{field}: "
                    f"expected {expected_value!r}, got {actual_value!r}"
                )
    expected_keys = {item.workload_key for item in expected}
    for actual_item in actual:
        if actual_item.workload_key not in expected_keys:
            failures.append(f"workload.{actual_item.workload_key}: unexpected actual outcome")
    return failures


def assert_expected_outcomes(
    *,
    expected: CorpusExpectedOutcomes,
    actual: CorpusExpectedOutcomes,
) -> list[str]:
    failures: list[str] = []
    if expected.workload_count != actual.workload_count:
        failures.append(
            f"workload_count: expected {expected.workload_count}, got {actual.workload_count}"
        )
    failures.extend(_diff_counts("motion_counts", expected.motion_counts, actual.motion_counts))
    failures.extend(_diff_counts("confidence_counts", expected.confidence_counts, actual.confidence_counts))
    failures.extend(
        _diff_counts(
            "identity_status_counts",
            expected.identity_status_counts,
            actual.identity_status_counts,
        )
    )
    failures.extend(_diff_counts("data_quality_codes", expected.data_quality_codes, actual.data_quality_codes))
    failures.extend(_diff_workloads(expected.workloads, actual.workloads))
    return failures


def sanitize_bundle_to_corpus(bundle_dir: Path, output_dir: Path) -> CorpusCase:
    result = analyze_bundle(bundle_dir, redact=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(bundle_dir)
    source_outputs = bundle_dir / manifest.outputs.directory
    fingerprints = source_outputs / manifest.outputs.fingerprints_json
    corpus_assessment = redact_assessment(
        result.assessment,
        salt="estate-triage-corpus",
        mode="standard",
    )
    write_assessment_json(output_dir / "assessment.json", corpus_assessment)
    if fingerprints.exists():
        (output_dir / "input-fingerprints.json").write_text(
            fingerprints.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    redacted = _load_assessment(output_dir / "assessment.json")
    thresholds = load_thresholds(
        bundle_dir / manifest.policy.thresholds if manifest.policy.thresholds else None
    )
    case = CorpusCase(
        source_bundle=str(bundle_dir),
        expected_summary=result.summary,
        thresholds=thresholds.model_dump(mode="json"),
        expected_outcomes=expected_outcomes_from_assessment(redacted),
    )
    (output_dir / "case.yml").write_text(
        yaml.safe_dump(case.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return case


def _corpus_case_paths(corpus_dir: Path) -> list[Path]:
    cases = sorted(corpus_dir.glob("*/case.yml"))
    if not cases and (corpus_dir / "case.yml").exists():
        cases = [corpus_dir / "case.yml"]
    return cases


def validate_sanitized_corpus(corpus_dir: Path) -> CorpusValidation:
    cases = _corpus_case_paths(corpus_dir)
    if not cases:
        raise TriageError(f"No corpus cases found in {corpus_dir}.")
    results: list[CorpusCaseValidation] = []
    for case_path in cases:
        errors: list[str] = []
        warnings: list[str] = []
        workloads = 0
        try:
            raw = yaml.safe_load(case_path.read_text(encoding="utf-8")) or {}
            case = CorpusCase(**raw)
        except Exception as exc:
            results.append(
                CorpusCaseValidation(
                    case=str(case_path.parent),
                    status="failed",
                    errors=[f"Invalid case.yml: {exc}"],
                )
            )
            continue

        assessment_path = case_path.parent / case.redacted_assessment
        fingerprint_path = case_path.parent / case.fingerprints
        if not assessment_path.exists():
            errors.append(f"Missing {case.redacted_assessment}.")
        else:
            try:
                assessment = _load_assessment(assessment_path)
                workloads = len(assessment.workloads)
                if workloads == 0:
                    errors.append("Assessment contains no workloads.")
            except TriageError as exc:
                errors.append(str(exc))
        if not fingerprint_path.exists():
            errors.append(f"Missing {case.fingerprints}.")
        if case.expected_outcomes is None:
            errors.append("Missing expected_outcomes.")
        elif case.expected_outcomes.workload_count != workloads:
            errors.append(
                "expected_outcomes.workload_count does not match assessment workload count."
            )
        if not case.thresholds:
            warnings.append("Case has no threshold snapshot.")
        results.append(
            CorpusCaseValidation(
                case=str(case_path.parent),
                status="passed" if not errors else "failed",
                workloads=workloads,
                errors=errors,
                warnings=warnings,
            )
        )

    error_count = sum(len(result.errors) for result in results)
    warning_count = sum(len(result.warnings) for result in results)
    return CorpusValidation(
        corpus_dir=str(corpus_dir),
        cases=len(results),
        status="passed" if error_count == 0 else "failed",
        errors=error_count,
        warnings=warning_count,
        results=results,
    )


def test_policy_against_corpus(policy_path: Path, corpus_dir: Path) -> dict:
    policy = load_policy_pack(policy_path)
    cases = _corpus_case_paths(corpus_dir)
    if not cases:
        raise TriageError(f"No corpus cases found in {corpus_dir}.")
    results = []
    total_failures = 0
    for case_path in cases:
        raw = yaml.safe_load(case_path.read_text(encoding="utf-8")) or {}
        case = CorpusCase(**raw)
        assessment_path = case_path.parent / case.redacted_assessment
        if not assessment_path.exists():
            raise TriageError(f"Corpus case {case_path} is missing {case.redacted_assessment}.")
        assessment = _load_assessment(assessment_path)
        failures: list[str] = []
        if case.expected_outcomes is None:
            failures.append("case.yml is missing expected_outcomes.")
        else:
            actual = _evaluate_expected_outcomes(
                assessment=assessment,
                thresholds=Thresholds(**case.thresholds),
                policy_path=policy_path,
            )
            failures.extend(
                assert_expected_outcomes(
                    expected=case.expected_outcomes,
                    actual=actual,
                )
            )
        total_failures += len(failures)
        results.append(
            {
                "case": str(case_path.parent),
                "policy_under_test": f"{policy.id}@{policy.version}",
                "stored_policy": f"{assessment.policy_id}@{assessment.policy_version}",
                "workloads": len(assessment.workloads),
                "status": "passed" if not failures else "failed",
                "failures": failures,
            }
        )
    return {
        "cases": len(results),
        "status": "passed" if total_failures == 0 else "failed",
        "failures": total_failures,
        "results": results,
    }
