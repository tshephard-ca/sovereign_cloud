from __future__ import annotations

from .models import QualificationResult, QuarantineRow


PRIMARY_REASON_PRIORITY = [
    "NVIDIA_SMI_QUERY_PARSE_FAILED",
    "NCCL_PARSE_FAILED",
    "BMC_SENSOR_PARSE_FAILED",
    "NCCL_CORRECTNESS_ERROR",
    "NCCL_WRONG_COUNT_NONZERO",
    "NCCL_TIMEOUT",
    "GPU_COUNT_BELOW_EXPECTED",
    "BMC_HEALTH_CRITICAL",
    "BMC_TEMP_CRITICAL",
    "BMC_FAN_FAILURE",
    "BMC_POWER_CRITICAL",
    "VBIOS_MISMATCH_DRAIN_POLICY",
]


def quarantine_row(result: QualificationResult) -> QuarantineRow:
    features = result.features
    recommendation = {
        "PASS": "NONE",
        "REVIEW": "REVIEW",
        "INFERENCE_ONLY": "INFERENCE_ONLY",
        "AVOID_MULTINODE": "AVOID_MULTINODE",
        "QUARANTINE": "QUARANTINE_REVIEW",
    }[result.qualification_status]
    severity = {
        "PASS": "INFO",
        "REVIEW": "REVIEW",
        "INFERENCE_ONLY": "WARNING",
        "AVOID_MULTINODE": "WARNING",
        "QUARANTINE": "CRITICAL",
    }[result.qualification_status]
    primary_reason = _primary_reason(features.blockers, features.warnings, features.reason_codes)
    suggested_state = "DRAIN" if recommendation in {"DRAIN_REVIEW", "QUARANTINE_REVIEW"} else "UNCHANGED"
    drain_reason = "" if suggested_state == "UNCHANGED" else _drain_reason(primary_reason)
    return QuarantineRow(
        node_name=features.node_name,
        recommendation=recommendation,
        severity=severity,
        confidence=features.confidence,
        primary_reason=primary_reason,
        reason_codes=";".join(features.reason_codes),
        blockers=";".join(features.blockers),
        suggested_slurm_state=suggested_state,
        suggested_drain_reason=drain_reason,
        safe_for_inference_candidate="gpu_inference_ok" in result.slurm_features,
        avoid_multinode_candidate="gpu_avoid_multinode" in result.slurm_features,
        operator_action=_operator_action(recommendation),
        suggested_operator_question=features.suggested_operator_question or "",
        source_evidence=";".join(features.source_evidence),
    )


def _drain_reason(primary_reason: str) -> str:
    reason = primary_reason.replace("_", " ").lower()
    return f"rackq: {reason}; review node before scheduling training jobs"


def _primary_reason(blockers: list[str], warnings: list[str], reason_codes: list[str]) -> str:
    combined = list(dict.fromkeys(blockers + warnings + reason_codes))
    for reason in PRIMARY_REASON_PRIORITY:
        if reason in combined:
            return reason
    return combined[0] if combined else "NONE"


def _operator_action(recommendation: str) -> str:
    return {
        "NONE": "No quarantine action suggested by current evidence.",
        "REVIEW": "Review warnings before broad scheduling.",
        "AVOID_MULTINODE": "Avoid multi-node training placement until reviewed.",
        "INFERENCE_ONLY": "Use inference-only placement only if site policy allows.",
        "DRAIN_REVIEW": "Review whether Slurm drain is appropriate.",
        "QUARANTINE_REVIEW": "Review whether the node should remain unscheduled.",
    }[recommendation]
