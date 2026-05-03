"""Markdown report generation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .junit import write_junit
from .decision import build_decision
from .models import RunResults


REASON_QUESTIONS = {
    "FORBIDDEN_CANARY_LEAKED": "Did the retrieval layer filter results by user permissions before the model saw context?",
    "FORBIDDEN_DOC_ID_CITED": "Are citations filtered after retrieval, or can the endpoint cite documents the user cannot access?",
    "FORBIDDEN_METADATA_LEAKED": "Is metadata filtered with the same permissions as document body text?",
    "FORBIDDEN_SNIPPET_LEAKED": "Are snippets generated before or after permission filtering?",
    "FORBIDDEN_RAW_CONTEXT_LEAKED": "Is raw retrieved context exposed in the API response for debugging or tracing?",
    "ALLOWED_EVIDENCE_MISSING": "Did the allowed document fail retrieval, or did the answer omit the expected canary evidence?",
    "RESPONSE_EXTRACTOR_MISSING_FIELD": "Did the endpoint response schema change, and should endpoint.yml be updated?",
    "NO_FORBIDDEN_TEST_CASES": "Do the test users have enough permission separation to create negative canary cases?",
    "NO_ALLOWED_TEST_CASES": "Do the test users have at least one document they are allowed to retrieve?",
    "CANARY_TEXT_NOT_UNIQUE": "Are canary tokens unique across documents so leakage can be attributed?",
    "AUTH_ENV_MISSING": "Are test-user credentials configured in environment variables for this run?",
}


def load_results(path: str | Path) -> RunResults:
    return RunResults.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def write_markdown_report(path: str | Path, results: RunResults) -> None:
    decision = results.decision or build_decision(results, results.business_context)
    lines = [
        "# RAG Permission Regression Report",
        "",
        "## Release Decision",
        "",
        f"Decision: **{decision.get('release_decision')}**",
        f"Aggregate status: **{results.aggregate_status}**",
        f"Confidence: **{decision.get('confidence')}**",
        f"Endpoint ID: `{results.endpoint_id}`",
        f"Content set ID: `{results.content_set_id}`",
        f"Recommended owner: `{decision.get('recommended_owner')}`",
        "",
        str(decision.get("summary", "")),
        "",
        f"Business risk: {decision.get('business_risk')}",
        "",
        "Coverage is limited to supplied users, content, queries, and endpoint behavior.",
        "",
        "## Tested Permission Boundaries",
        "",
        f"- Tested boundaries: {decision.get('tested_boundaries', 0)}",
        f"- Users tested: {results.summary.get('users_tested', 0)}",
        f"- Tests: {results.summary.get('test_count', 0)}",
        f"- Allowed tests: {results.summary.get('allowed_test_count', 0)}",
        f"- Forbidden tests: {results.summary.get('forbidden_test_count', 0)}",
        f"- Pass: {results.summary.get('pass_count', 0)}",
        f"- Fail: {results.summary.get('fail_count', 0)}",
        f"- Review: {results.summary.get('review_count', 0)}",
        f"- Skipped: {results.summary.get('skipped_count', 0)}",
        "",
        "## Leak Surface Summary",
        "",
        "- Surfaces tested: " + (", ".join(decision.get("surfaces_tested", [])) or "none observed"),
        "- Surfaces not observed: " + (", ".join(decision.get("surfaces_not_observed", [])) or "none recorded"),
        "",
        "## Leakage Counts",
        "",
    ]
    for key, value in results.leakage_summary.items():
        lines.append(f"- {key}: {value}")
    _table(lines, "Failures Requiring Action", [item for item in results.test_results if item.status == "FAIL"])
    _table(lines, "Review Items And Missing Evidence", [item for item in results.test_results if item.status in {"REVIEW", "SKIPPED"}])
    _table(lines, "Allowed Access Utility Checks", [item for item in results.test_results if item.expected_result == "ALLOWED" and item.status != "SKIPPED"])
    reason_counts = Counter(reason for item in results.test_results for reason in item.reason_codes)
    lines.extend(["", "## Top Reason Codes", ""])
    for reason, count in reason_counts.most_common(20):
        lines.append(f"- `{reason}`: {count}")
    missing = sorted(set(warning for item in results.test_results for warning in item.warnings if "MISSING" in warning))
    lines.extend(["", "## Missing Data", ""])
    if missing:
        lines.extend(f"- `{item}`" for item in missing)
    else:
        lines.append("- none recorded")
    questions = _questions(results)
    lines.extend(["", "## Recommended Next Questions", ""])
    if questions:
        lines.extend(f"- {question}" for question in questions)
    else:
        lines.append("- No leakage-specific follow-up question was generated.")
    lines.extend(
        [
            "",
            "## Data Honesty Caveats",
            "",
            "- A canary pack tests only supplied users, documents, permissions, and queries.",
            "- Exact canary matching does not detect all paraphrased leakage.",
            "- Absence of a canary leak does not prove the whole endpoint is protected.",
            "- Synthetic content may not match production retrieval behavior.",
            "- The endpoint must already be configured to use the intended identity context.",
            "- The tool does not verify identity-provider, connector, index, or model internals.",
            "- Missing citations limit confidence.",
            "- User-supplied permissions may not reflect real production permissions.",
            "- Query wording can affect retrieval behavior.",
            "- This is a regression test, not an access-control implementation.",
        ]
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _table(lines: list[str], title: str, rows: list) -> None:
    lines.extend(["", f"## {title}", ""])
    if not rows:
        lines.append("- none")
        return
    lines.extend(["| test_case_id | user_id | target_doc_id | reason_codes |", "|---|---|---|---|"])
    for item in rows:
        lines.append(f"| {item.test_case_id} | {item.user_id} | {item.target_doc_id} | {' '.join(item.reason_codes)} |")


def _questions(results: RunResults) -> list[str]:
    questions: list[str] = []
    for item in results.test_results:
        for reason in item.reason_codes:
            question = REASON_QUESTIONS.get(reason)
            if question and question not in questions:
                questions.append(question)
    return questions
