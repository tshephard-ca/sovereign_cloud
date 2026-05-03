"""Run canary packs and score deterministic leakage results."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import uuid

import httpx

from .canary_generate import load_pack
from .config import load_config
from .content_set import canary_text_by_id, document_by_id, load_content_set
from .decision import build_decision
from .evidence import SAMPLES_COLUMNS
from .endpoint_profile import load_endpoint_profile
from .http_client import send_test_request
from .leakage_detect import allowed_evidence_found, detect_leakage
from .models import CanaryPack, EndpointProfile, ExtractedResponse, RunResults, TestResult, TestUsers
from .redact import redact_id, redact_results, redact_text
from .response_extract import extract_response
from .users import load_users, user_by_id


def run_pack(
    *,
    pack: CanaryPack,
    endpoint: EndpointProfile,
    users: TestUsers,
    content_path: str | Path | None = None,
    config: dict | None = None,
    strict: bool = False,
    dry_run: bool = False,
    no_network: bool = False,
    timeout_seconds: int | None = None,
    now: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> RunResults:
    config = config or load_config(None)
    timeout_seconds = timeout_seconds or int(config.get("request_timeout_seconds", 60))
    started = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    users_by_id = user_by_id(users)
    allowed_canaries: dict[str, str] = {}
    titles: dict[str, str] = {}
    if content_path:
        content = load_content_set(content_path)
        allowed_canaries = canary_text_by_id(content)
        titles = {doc.doc_id: doc.title for doc in content.documents}
    results: list[TestResult] = []
    blockers: list[str] = []
    warnings: list[str] = list(pack.warnings)
    for case in pack.test_cases:
        user = users_by_id.get(case.user_id)
        if user is None:
            results.append(_skipped(case, "NO_TEST_USERS"))
            continue
        endpoint_response, request_reasons = send_test_request(
            profile=endpoint,
            test_case=case,
            user=user,
            timeout_seconds=timeout_seconds,
            strict=strict,
            dry_run=dry_run,
            no_network=no_network,
            transport=transport,
        )
        if dry_run or no_network:
            results.append(_skipped(case, request_reasons[0]))
            continue
        if endpoint_response.http_status in {401, 403}:
            results.append(
                TestResult(
                    test_case_id=case.test_case_id,
                    user_id=case.user_id,
                    expected_result=case.expected_result,
                    status="FAIL",
                    http_status=endpoint_response.http_status,
                    latency_ms=endpoint_response.latency_ms,
                    target_doc_id=case.target_doc_id,
                    reason_codes=_unique(request_reasons + ["HTTP_AUTH_FAILURE", "PERMISSION_REGRESSION_FAIL"]),
                    warnings=endpoint_response.warnings,
                )
            )
            continue
        if endpoint_response.error:
            status = "FAIL" if strict or config.get("strict_endpoint_errors_fail") else "REVIEW"
            results.append(
                TestResult(
                    test_case_id=case.test_case_id,
                    user_id=case.user_id,
                    expected_result=case.expected_result,
                    status=status,
                    target_doc_id=case.target_doc_id,
                    reason_codes=_unique(request_reasons + (["PERMISSION_REGRESSION_FAIL"] if status == "FAIL" else ["HUMAN_REVIEW_REQUIRED"])),
                    warnings=endpoint_response.warnings,
                )
            )
            continue
        extracted = extract_response(endpoint_response.json_body if endpoint_response.json_body is not None else {}, endpoint)
        reason_codes = _unique(request_reasons + ["RESPONSE_EXTRACTED"] + [warning for warning in extracted.warnings if warning.startswith("RESPONSE_")])
        leakage, leak_reasons, leak_warnings = detect_leakage(case, extracted, config)
        reason_codes = _unique(reason_codes + leak_reasons)
        case_warnings = _unique(endpoint_response.warnings + extracted.warnings + leak_warnings)
        status = _score_case(case, extracted, leakage, allowed_canaries, titles, config, reason_codes, case_warnings)
        results.append(
            TestResult(
                test_case_id=case.test_case_id,
                user_id=case.user_id,
                expected_result=case.expected_result,
                status=status,
                http_status=endpoint_response.http_status,
                latency_ms=endpoint_response.latency_ms,
                target_doc_id=case.target_doc_id,
                leakage_findings=leakage,
                reason_codes=reason_codes,
                warnings=case_warnings,
                answer_excerpt_redacted=redact_text(extracted.answer_text, max_chars=int(config["reporting"].get("max_answer_excerpt_chars", 180))),
                citation_doc_ids_redacted=[redact_id(doc_id, "doc") for doc_id in extracted.citation_doc_ids],
            )
        )
    aggregate = _aggregate(results)
    if not results:
        aggregate = "INSUFFICIENT_DATA"
        blockers.append("NO_TESTS_RAN")
    finished = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_results = RunResults(
        run_id=str(uuid.uuid5(uuid.NAMESPACE_URL, pack.pack_id + started + endpoint.endpoint_id)),
        pack_id=pack.pack_id,
        content_set_id=pack.content_set_id,
        endpoint_id=endpoint.endpoint_id,
        started_at=started,
        finished_at=finished,
        aggregate_status=aggregate,
        summary=_summary(results),
        leakage_summary=_leakage_summary(results),
        business_context=dict(config.get("business_context", {})),
        test_results=results,
        warnings=_unique(warnings + [warning for result in results for warning in result.warnings]),
        blockers=blockers,
    )
    run_results.decision = build_decision(run_results, dict(config.get("business_context", {})))
    return run_results


def run_from_files(
    *,
    pack_path: str | Path,
    endpoint_path: str | Path,
    users_path: str | Path | None = None,
    content_path: str | Path | None = None,
    config_path: str | Path | None = None,
    strict: bool = False,
    dry_run: bool = False,
    no_network: bool = False,
    timeout_seconds: int | None = None,
    now: str | None = None,
) -> RunResults:
    pack = load_pack(pack_path)
    endpoint = load_endpoint_profile(endpoint_path, strict=strict)
    users = load_users(users_path, strict=strict) if users_path is not None else TestUsers(users=pack.test_users)
    if not users.users:
        raise ValueError("NO_TEST_USERS")
    return run_pack(
        pack=pack,
        endpoint=endpoint,
        users=users,
        content_path=content_path,
        config=load_config(config_path),
        strict=strict,
        dry_run=dry_run,
        no_network=no_network,
        timeout_seconds=timeout_seconds,
        now=now,
    )


def write_results_json(path: str | Path, results: RunResults, *, redact: bool = False) -> None:
    output = redact_results(results) if redact else results
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(output.model_dump(), indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_samples_csv(path: str | Path, results: RunResults, *, redact: bool = False) -> None:
    output = redact_results(results) if redact else results
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLES_COLUMNS)
        writer.writeheader()
        for result in output.test_results:
            writer.writerow(
                {
                    "test_case_id": result.test_case_id,
                    "user_id": result.user_id,
                    "expected_result": result.expected_result,
                    "status": result.status,
                    "http_status": result.http_status,
                    "latency_ms": result.latency_ms,
                    "target_doc_id": result.target_doc_id,
                    "leaked_forbidden_doc_ids": "|".join(finding.forbidden_doc_id for finding in result.leakage_findings if finding.forbidden_doc_id),
                    "leaked_forbidden_canary_ids": "|".join(finding.canary_id for finding in result.leakage_findings if finding.canary_id),
                    "citation_doc_ids_redacted": "|".join(result.citation_doc_ids_redacted),
                    "answer_excerpt_redacted": result.answer_excerpt_redacted,
                    "reason_codes": "|".join(result.reason_codes),
                    "warnings": "|".join(result.warnings),
                }
            )


def _score_case(case, extracted: ExtractedResponse, leakage, allowed_canaries, titles, config, reason_codes: list[str], warnings: list[str]) -> str:
    if leakage:
        reason_codes.extend(["PERMISSION_REGRESSION_FAIL"])
        return "FAIL"
    if case.expected_result == "FORBIDDEN":
        reason_codes.extend(["FORBIDDEN_QUERY_EXECUTED", "PERMISSION_REGRESSION_PASS"])
        return "PASS"
    reason_codes.append("ALLOWED_QUERY_EXECUTED")
    if not extracted.answer_text:
        warnings.append("ANSWER_TEXT_MISSING")
        reason_codes.append("ALLOWED_EVIDENCE_MISSING")
        return "REVIEW" if config["allowed_checks"].get("allowed_empty_answer_is_review", True) else "FAIL"
    if allowed_evidence_found(case, extracted, allowed_canaries, titles):
        reason_codes.extend(["ALLOWED_EVIDENCE_FOUND", "PERMISSION_REGRESSION_PASS"])
        return "PASS"
    reason_codes.extend(["ALLOWED_EVIDENCE_MISSING", "HUMAN_REVIEW_REQUIRED"])
    warnings.append("ALLOWED_QUERY_LACKS_POSITIVE_EVIDENCE")
    return "REVIEW"


def _aggregate(results: list[TestResult]) -> str:
    if not results:
        return "INSUFFICIENT_DATA"
    if any(result.status == "FAIL" for result in results):
        return "FAIL"
    if any(result.status in {"REVIEW", "SKIPPED"} for result in results):
        return "REVIEW"
    allowed_by_user = {(result.user_id, result.expected_result) for result in results if result.status == "PASS"}
    users = {result.user_id for result in results}
    if not all((user, "ALLOWED") in allowed_by_user and (user, "FORBIDDEN") in allowed_by_user for user in users):
        return "REVIEW"
    return "PASS"


def _summary(results: list[TestResult]) -> dict[str, int]:
    return {
        "test_count": len(results),
        "pass_count": sum(result.status == "PASS" for result in results),
        "fail_count": sum(result.status == "FAIL" for result in results),
        "review_count": sum(result.status == "REVIEW" for result in results),
        "skipped_count": sum(result.status == "SKIPPED" for result in results),
        "allowed_test_count": sum(result.expected_result == "ALLOWED" for result in results),
        "forbidden_test_count": sum(result.expected_result == "FORBIDDEN" for result in results),
        "users_tested": len({result.user_id for result in results}),
        "documents_tested": len({result.target_doc_id for result in results if result.target_doc_id}),
    }


def _leakage_summary(results: list[TestResult]) -> dict[str, int]:
    findings = [finding for result in results for finding in result.leakage_findings]
    return {
        "forbidden_canary_leaks": sum("CANARY" in finding.leakage_type for finding in findings),
        "forbidden_doc_id_citations": sum("DOC_ID" in finding.leakage_type for finding in findings),
        "forbidden_title_leaks": sum("TITLE" in finding.leakage_type for finding in findings),
        "forbidden_metadata_leaks": sum("METADATA" in finding.leakage_type for finding in findings),
        "forbidden_snippet_leaks": sum("SNIPPET" in finding.leakage_type for finding in findings),
        "forbidden_raw_context_leaks": sum("RAW_CONTEXT" in finding.leakage_type for finding in findings),
    }


def _skipped(case, reason: str) -> TestResult:
    return TestResult(
        test_case_id=case.test_case_id,
        user_id=case.user_id,
        expected_result=case.expected_result,
        status="SKIPPED",
        target_doc_id=case.target_doc_id,
        reason_codes=[reason],
        warnings=[reason],
    )


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
