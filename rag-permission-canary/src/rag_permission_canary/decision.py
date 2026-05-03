"""Release-decision summary for permission canary runs."""

from __future__ import annotations

from .models import RunResults


SURFACE_WARNING_MAP = {
    "answer": "ANSWER_TEXT_MISSING",
    "citations": "CITATIONS_MISSING",
    "raw_context": "RAW_CONTEXT_MISSING",
}


def build_decision(results: RunResults, business_context: dict | None = None) -> dict[str, object]:
    business_context = business_context or {}
    executed_results = [result for result in results.test_results if result.status != "SKIPPED"] or results.test_results
    surfaces_tested = ["answer", "citations", "snippets", "metadata", "raw_context"]
    surfaces_not_observed = [
        surface
        for surface, warning in SURFACE_WARNING_MAP.items()
        if executed_results and all(warning in result.warnings for result in executed_results)
    ]
    leak_channels = [key for key, count in sorted(results.leakage_summary.items()) if count]
    boundary_count = len({(result.user_id, result.target_doc_id, result.expected_result) for result in results.test_results if result.target_doc_id})
    release_decision = _release_decision(results.aggregate_status)
    confidence = _confidence(results, surfaces_not_observed, leak_channels)
    owner = _recommended_owner(results, leak_channels)
    summary = _summary_text(results, release_decision, leak_channels, surfaces_not_observed)
    return {
        "release_decision": release_decision,
        "business_risk": _business_risk(results.aggregate_status, leak_channels, surfaces_not_observed),
        "confidence": confidence,
        "tested_boundaries": boundary_count,
        "surfaces_tested": [surface for surface in surfaces_tested if surface not in surfaces_not_observed],
        "surfaces_not_observed": surfaces_not_observed,
        "leak_channels": leak_channels,
        "recommended_owner": owner,
        "summary": summary,
        "business_context": business_context,
    }


def _release_decision(status: str) -> str:
    return {
        "PASS": "ALLOW_NEXT_STAGE",
        "FAIL": "BLOCK_RELEASE",
        "REVIEW": "HUMAN_REVIEW_REQUIRED",
        "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
    }.get(status, "HUMAN_REVIEW_REQUIRED")


def _confidence(results: RunResults, surfaces_not_observed: list[str], leak_channels: list[str]) -> str:
    if results.aggregate_status == "FAIL" and leak_channels:
        return "HIGH"
    if results.aggregate_status == "PASS" and not surfaces_not_observed:
        return "HIGH"
    if results.aggregate_status in {"PASS", "FAIL"}:
        return "MEDIUM"
    return "LOW"


def _recommended_owner(results: RunResults, leak_channels: list[str]) -> str:
    reasons = {reason for result in results.test_results for reason in result.reason_codes}
    if "HTTP_AUTH_FAILURE" in reasons or "AUTH_ENV_MISSING" in reasons:
        return "iam_or_endpoint_auth_owner"
    if any("raw_context" in channel or "citation" in channel or "metadata" in channel or "snippet" in channel for channel in leak_channels):
        return "retrieval_endpoint_owner"
    if "ALLOWED_EVIDENCE_MISSING" in reasons:
        return "retrieval_index_owner"
    if results.aggregate_status == "FAIL":
        return "ai_platform_owner"
    return "release_owner"


def _business_risk(status: str, leak_channels: list[str], surfaces_not_observed: list[str]) -> str:
    if status == "FAIL":
        channels = ", ".join(channel.replace("_", " ") for channel in leak_channels) or "forbidden evidence"
        return f"Forbidden evidence appeared through tested response surfaces: {channels}."
    if status == "REVIEW":
        missing = ", ".join(surfaces_not_observed) or "required evidence"
        return f"The run did not produce enough evidence for a release decision; missing or ambiguous surfaces: {missing}."
    if status == "INSUFFICIENT_DATA":
        return "The canary run did not execute enough tests to support a release decision."
    return "Tested permission boundaries produced no forbidden evidence and allowed access produced positive evidence."


def _summary_text(results: RunResults, release_decision: str, leak_channels: list[str], surfaces_not_observed: list[str]) -> str:
    tests = results.summary.get("test_count", len(results.test_results))
    failures = results.summary.get("fail_count", 0)
    reviews = results.summary.get("review_count", 0) + results.summary.get("skipped_count", 0)
    if release_decision == "BLOCK_RELEASE":
        return f"Block release: {failures} of {tests} tests failed with leak channels {', '.join(leak_channels) or 'forbidden evidence'}."
    if release_decision == "HUMAN_REVIEW_REQUIRED":
        return f"Human review required: {reviews} of {tests} tests lacked enough release-gate evidence."
    if release_decision == "INSUFFICIENT_DATA":
        return "Insufficient data: no reliable permission-regression decision can be made from this run."
    observed = "all configured surfaces" if not surfaces_not_observed else "observed surfaces"
    return f"Allow next stage for tested boundaries: {tests} tests passed across {observed}."
