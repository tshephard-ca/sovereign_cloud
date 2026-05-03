"""Fixture quality and coverage assessment."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .access_matrix import build_access_matrix
from .models import CanaryPack, ContentSet, EndpointProfile, PermissionModel, TestUsers


def assess_fixture(
    content: ContentSet,
    users: TestUsers,
    permissions: PermissionModel,
    endpoint: EndpointProfile,
    config: dict,
    pack: CanaryPack | None = None,
) -> dict[str, object]:
    matrix = build_access_matrix(content, users, permissions, config, pack)
    canary_texts = [canary.text for doc in content.documents for canary in doc.canaries]
    metadata_values = [str(value) for doc in content.documents for value in doc.metadata.values() if value]
    evidence_metadata_values = [
        str(value)
        for doc in content.documents
        for key, value in doc.metadata.items()
        if value and key not in {"department", "record_type", "category", "type"}
    ]
    repeated_metadata = sorted(value for value, count in Counter(evidence_metadata_values).items() if count > 1)
    allowed_pairs = sum(row["expected_access"] == "ALLOWED" for row in matrix)
    forbidden_pairs = sum(row["expected_access"] == "FORBIDDEN" for row in matrix)
    users_with_both = _users_with_both(matrix)
    warnings: list[str] = []
    blockers: list[str] = []
    reason_codes = ["CONTENT_SET_VALID", "USERS_VALID", "PERMISSIONS_VALID", "ENDPOINT_VALID"]
    if not content.documents:
        blockers.append("NO_DOCUMENTS")
    if not users.users:
        blockers.append("NO_TEST_USERS")
    if not canary_texts:
        blockers.append("NO_CANARIES")
    if allowed_pairs == 0:
        blockers.append("NO_ALLOWED_TEST_CASES")
    if forbidden_pairs == 0:
        blockers.append("NO_FORBIDDEN_TEST_CASES")
    if len(canary_texts) != len(set(canary_texts)):
        blockers.append("CANARY_TEXT_NOT_UNIQUE")
    if users_with_both < len(users.users):
        warnings.append("USER_WITHOUT_BOTH_ALLOWED_AND_FORBIDDEN_DOCS")
    if repeated_metadata:
        warnings.append("METADATA_MARKER_NOT_UNIQUE")
    if pack and len(pack.test_cases) < int(config.get("default_total_queries", 20)):
        warnings.append("SMALL_TEST_PACK")
    if endpoint.behavior.fail_on_forbidden_metadata and not metadata_values:
        warnings.append("METADATA_SELECTOR_NOT_IMPLEMENTED")
    if endpoint.response_extractors.raw_context_json_path:
        reason_codes.append("RAW_CONTEXT_CHECK_CONFIGURED")
    if endpoint.response_extractors.citations_json_path:
        reason_codes.append("CITATION_CHECK_CONFIGURED")
    if endpoint.response_extractors.metadata_json_path:
        reason_codes.append("METADATA_CHECK_CONFIGURED")
    grade = _grade(blockers, warnings, allowed_pairs, forbidden_pairs, users_with_both)
    return {
        "schema_version": "rag_permission_canary.fixture_quality.v1",
        "valid": not blockers,
        "quality_grade": grade,
        "summary": {
            "users": len(users.users),
            "documents": len(content.documents),
            "documents_with_canaries": sum(bool(doc.canaries) for doc in content.documents),
            "canary_count": len(canary_texts),
            "unique_canary_count": len(set(canary_texts)),
            "allowed_user_doc_pairs": allowed_pairs,
            "forbidden_user_doc_pairs": forbidden_pairs,
            "users_with_allowed_and_forbidden_docs": users_with_both,
            "generated_test_cases": len(pack.test_cases) if pack else 0,
        },
        "surface_coverage": {
            "answer": bool(endpoint.response_extractors.answer_text_json_path),
            "citations": bool(endpoint.response_extractors.citations_json_path),
            "citation_doc_ids": bool(endpoint.response_extractors.citation_doc_id_json_path),
            "citation_titles": bool(endpoint.response_extractors.citation_title_json_path),
            "snippets": bool(endpoint.response_extractors.citation_snippet_json_path),
            "metadata": bool(endpoint.response_extractors.metadata_json_path),
            "raw_context": bool(endpoint.response_extractors.raw_context_json_path),
        },
        "metadata_quality": {
            "metadata_values": len(metadata_values),
            "unique_metadata_values": len(set(metadata_values)),
            "repeated_metadata_values": repeated_metadata[:20],
        },
        "warnings": warnings,
        "blockers": blockers,
        "reason_codes": reason_codes,
    }


def write_fixture_quality_json(path: str | Path, report: dict[str, object]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_fixture_quality_markdown(path: str | Path, report: dict[str, object]) -> None:
    summary = report.get("summary", {})
    lines = [
        "# RAG Permission Canary Fixture Quality",
        "",
        f"Quality grade: **{report.get('quality_grade')}**",
        f"Valid for gating: **{report.get('valid')}**",
        "",
        "## Coverage",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Surface Coverage", ""])
    for key, value in dict(report.get("surface_coverage", {})).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Warnings", ""])
    warnings = list(report.get("warnings", []))
    lines.extend([f"- `{warning}`" for warning in warnings] if warnings else ["- none"])
    lines.extend(["", "## Blockers", ""])
    blockers = list(report.get("blockers", []))
    lines.extend([f"- `{blocker}`" for blocker in blockers] if blockers else ["- none"])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _users_with_both(matrix: list[dict[str, object]]) -> int:
    by_user: dict[str, set[str]] = {}
    for row in matrix:
        by_user.setdefault(str(row["user_id"]), set()).add(str(row["expected_access"]))
    return sum({"ALLOWED", "FORBIDDEN"}.issubset(values) for values in by_user.values())


def _grade(blockers: list[str], warnings: list[str], allowed: int, forbidden: int, users_with_both: int) -> str:
    if blockers:
        return "BLOCKED"
    if allowed >= 10 and forbidden >= 10 and users_with_both >= 2 and not warnings:
        return "STRONG"
    if allowed >= 5 and forbidden >= 5 and users_with_both >= 2:
        return "USABLE"
    return "WEAK"
