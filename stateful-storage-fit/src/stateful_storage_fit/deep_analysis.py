from __future__ import annotations

from .classify_processes import ProcessClassification
from .constraint_solver import solve_compatibility
from .evidence import build_evidence_graph
from .evidence_planner import plan_evidence_questions
from .models import CandidateDataMount, DeepFitAnalysis, FitResult, IoDeviceSample, StorageProfile, model_to_dict
from .requirement_model import build_behavior_fingerprint, build_enhanced_requirement


def build_deep_analysis(
    *,
    fit_result: FitResult,
    candidates: list[CandidateDataMount],
    process_info: ProcessClassification,
    profile: StorageProfile | None,
    iostat_samples: dict[str, IoDeviceSample],
    missing_data: list[str],
    parse_warnings: list[str],
    extra_evidence: dict | None = None,
) -> DeepFitAnalysis:
    graph = build_evidence_graph(
        candidates=candidates,
        process_info=process_info,
        iostat_samples=iostat_samples,
        missing_data=missing_data,
        parse_warnings=parse_warnings,
        fit_reason_codes=fit_result.reason_codes,
        extra_evidence=extra_evidence,
    )
    fingerprint = build_behavior_fingerprint(
        candidates=candidates,
        process_info=process_info,
        graph=graph,
        fit_result=fit_result,
    )
    requirement = build_enhanced_requirement(fit_result=fit_result, fingerprint=fingerprint)
    compatibility = solve_compatibility(profile, requirement)
    questions = plan_evidence_questions(
        fit_result=fit_result,
        candidates=candidates,
        process_info=process_info,
        fingerprint=fingerprint,
    )
    decision_drivers = []
    if fit_result.blockers:
        decision_drivers.extend(f"blocker:{blocker}" for blocker in fit_result.blockers)
    if fit_result.warnings:
        decision_drivers.extend(f"warning:{warning}" for warning in fit_result.warnings)
    decision_drivers.extend(f"reason:{code}" for code in fit_result.reason_codes[:8])
    return DeepFitAnalysis(
        evidence_graph=graph,
        behavior_fingerprint=fingerprint,
        enhanced_requirement=requirement,
        compatibility=compatibility,
        evidence_questions=questions,
        decision_drivers=decision_drivers,
    )


def attach_deep_analysis(result: FitResult, analysis: DeepFitAnalysis) -> FitResult:
    result.analysis = model_to_dict(analysis)
    return result

