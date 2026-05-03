from __future__ import annotations

import hashlib
from typing import Any

from .models import Mismatch, Probe
from .impact import business_impact_for_code, question_for_code


def compare_step(probe: Probe, operation: str, expected: dict[str, Any], actual: dict[str, Any]) -> list[Mismatch]:
    mismatches: list[Mismatch] = []
    evidence = "+".join(probe.evidence_source) if probe.evidence_source else "SYNTHETIC_PROBE"
    if "status" in expected and isinstance(expected["status"], int):
        actual_status = actual.get("status_code")
        if actual_status != expected["status"]:
            mismatches.append(
                make_mismatch(
                    probe,
                    operation,
                    evidence,
                    str(expected["status"]),
                    str(actual_status),
                    "STATUS_CODE_MISMATCH",
                    f"Target returned status {actual_status}; expected {expected['status']}.",
                )
            )
    if expected.get("error_code"):
        actual_error = actual.get("error_code")
        if actual_error and actual_error != expected["error_code"]:
            mismatches.append(
                make_mismatch(
                    probe,
                    operation,
                    evidence,
                    str(expected["error_code"]),
                    str(actual_error),
                    "ERROR_CODE_MISMATCH",
                    "Target returned a different S3 error code.",
                    severity="REVIEW",
                )
            )
    headers = {str(k).lower(): str(v) for k, v in (actual.get("headers") or {}).items()}
    for name, value in (expected.get("headers") or {}).items():
        actual_value = headers.get(name.lower())
        if actual_value is None:
            mismatches.append(
                make_mismatch(
                    probe,
                    operation,
                    evidence,
                    f"{name} present",
                    "header absent",
                    "CRITICAL_HEADER_MISSING",
                    f"Target did not return expected header {name}.",
                    severity="REVIEW",
                )
            )
        elif str(value).lower() not in actual_value.lower():
            mismatches.append(
                make_mismatch(
                    probe,
                    operation,
                    evidence,
                    f"{name}: {value}",
                    f"{name}: {actual_value}",
                    "CRITICAL_HEADER_VALUE_MISMATCH",
                    f"Target returned a different value for {name}.",
                    severity="REVIEW",
                )
            )
    if expected.get("body_sha256"):
        digest = hashlib.sha256(actual.get("body") or b"").hexdigest()
        if digest != expected["body_sha256"]:
            mismatches.append(
                make_mismatch(
                    probe,
                    operation,
                    evidence,
                    expected["body_sha256"],
                    digest,
                    "RESPONSE_BODY_HASH_MISMATCH",
                    "Synthetic object body did not round trip.",
                )
            )
    if expected.get("tags"):
        actual_tags = _extract_tags(actual)
        for key, value in expected["tags"].items():
            if actual_tags.get(key) != value:
                mismatches.append(
                    make_mismatch(
                        probe,
                        operation,
                        evidence,
                        f"{key}={value}",
                        f"{key}={actual_tags.get(key)}",
                        "TAGGING_ROUNDTRIP_FAILED",
                        "Synthetic object tags did not round trip.",
                    )
                )
    if expected.get("metadata"):
        actual_metadata = _extract_metadata(actual)
        for key, value in expected["metadata"].items():
            if actual_metadata.get(str(key).lower()) != value:
                mismatches.append(
                    make_mismatch(
                        probe,
                        operation,
                        evidence,
                        f"{key}={value}",
                        f"{key}={actual_metadata.get(str(key).lower())}",
                        "METADATA_ROUNDTRIP_FAILED",
                        "Synthetic object metadata did not round trip.",
                    )
                )
    if expected.get("body_length") is not None:
        actual_length = len(actual.get("body") or b"")
        if actual_length != expected["body_length"]:
            mismatches.append(
                make_mismatch(
                    probe,
                    operation,
                    evidence,
                    str(expected["body_length"]),
                    str(actual_length),
                    "RESPONSE_BODY_HASH_MISMATCH",
                    "Synthetic range response length did not match.",
                )
            )
    if expected.get("continuation_token_present"):
        data = actual.get("data") or {}
        if not (data.get("NextContinuationToken") or data.get("IsTruncated")):
            mismatches.append(
                make_mismatch(
                    probe,
                    operation,
                    evidence,
                    "continuation token present",
                    "continuation token absent",
                    "LIST_PAGINATION_TOKEN_MISSING",
                    "Target did not return expected pagination continuation behavior.",
                    severity="REVIEW",
                )
            )
    if expected.get("delete_marker_present"):
        data = actual.get("data") or {}
        if not data.get("DeleteMarkers"):
            mismatches.append(
                make_mismatch(
                    probe,
                    operation,
                    evidence,
                    "delete marker present",
                    "delete marker absent",
                    "DELETE_MARKER_BEHAVIOR_MISMATCH",
                    "Target did not expose expected delete marker behavior.",
                )
            )
    if expected.get("cors"):
        mismatches.extend(compare_cors(probe, operation, evidence, expected["cors"], actual))
    return mismatches


def compare_cors(probe: Probe, operation: str, evidence: str, expected: dict[str, Any], actual: dict[str, Any]) -> list[Mismatch]:
    headers = {str(k).lower(): str(v) for k, v in (actual.get("headers") or {}).items()}
    mismatches: list[Mismatch] = []
    origin = expected.get("origin")
    method = expected.get("method")
    if origin and "access-control-allow-origin" not in headers:
        mismatches.append(
            make_mismatch(
                probe,
                operation,
                evidence,
                "Access-Control-Allow-Origin present",
                "header absent",
                "CORS_PREFLIGHT_MISMATCH",
                "Target did not return expected CORS allow-origin header.",
            )
        )
    if method and "access-control-allow-methods" not in headers:
        mismatches.append(
            make_mismatch(
                probe,
                operation,
                evidence,
                "Access-Control-Allow-Methods present",
                "header absent",
                "CORS_PREFLIGHT_MISMATCH",
                "Target did not return expected CORS allow-methods header.",
            )
        )
    return mismatches


def make_mismatch(
    probe: Probe,
    operation: str,
    evidence: str,
    expected: str,
    actual: str,
    code: str,
    reason: str,
    severity: str | None = None,
) -> Mismatch:
    sev = severity or ("BLOCKER" if probe.required else "REVIEW")
    return Mismatch(
        severity=sev,
        probe_id=probe.id,
        operation_family=probe.family,
        operation=operation,
        evidence_source=evidence,
        expected=expected,
        actual=actual,
        mismatch_code=code,
        reason_text=reason,
        business_impact=business_impact_for_code(code),
        suggested_human_question=question_for_code(code),
    )


def _extract_tags(actual: dict[str, Any]) -> dict[str, str]:
    data = actual.get("data") or {}
    tag_set = data.get("TagSet") or []
    return {item.get("Key"): item.get("Value") for item in tag_set if isinstance(item, dict)}


def _extract_metadata(actual: dict[str, Any]) -> dict[str, str]:
    data = actual.get("data") or {}
    metadata = data.get("Metadata") or data.get("metadata") or {}
    headers = {str(k).lower(): str(v) for k, v in (actual.get("headers") or {}).items()}
    output = {str(k).lower(): str(v) for k, v in metadata.items()}
    for key, value in headers.items():
        if key.startswith("x-amz-meta-"):
            output[key.replace("x-amz-meta-", "", 1)] = value
    return output

