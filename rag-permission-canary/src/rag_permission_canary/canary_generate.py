"""Deterministic canary pack generation."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import load_config
from .content_set import document_by_id
from .evidence import CANARY_QUERY_COLUMNS
from .models import CanaryPack, CanaryTestCase, ContentSet, Document, LeakageCheck, PermissionModel, TestUsers
from .permissions import expected_access
from .query_templates import allowed_query, forbidden_query


def generate_canary_pack(
    *,
    content: ContentSet,
    users: TestUsers,
    permissions: PermissionModel,
    queries_per_user: int = 10,
    config: dict | None = None,
    now: str | None = None,
    strict: bool = False,
) -> CanaryPack:
    config = config or load_config(None)
    target_total = min(int(config.get("default_total_queries", 20)), max(1, queries_per_user) * len(users.users))
    target_allowed = target_total // 2
    target_forbidden = target_total - target_allowed
    allowed_candidates: list[CanaryTestCase] = []
    forbidden_candidates: list[CanaryTestCase] = []
    docs = sorted(content.documents, key=lambda doc: doc.doc_id)
    for user in sorted(users.users, key=lambda item: item.user_id):
        allowed_doc_ids = [doc.doc_id for doc in docs if expected_access(user, doc, permissions, config) == "ALLOWED"]
        forbidden_doc_ids = [doc.doc_id for doc in docs if expected_access(user, doc, permissions, config) == "FORBIDDEN"]
        for doc in docs:
            access = expected_access(user, doc, permissions, config)
            if access == "ALLOWED" and doc.canaries:
                canary = sorted(doc.canaries, key=lambda item: item.canary_id)[0]
                allowed_candidates.append(
                    CanaryTestCase(
                        test_case_id="pending",
                        user_id=user.user_id,
                        query=allowed_query(doc, canary.text, len(allowed_candidates)),
                        expected_result="ALLOWED",
                        target_doc_id=doc.doc_id,
                        target_canary_ids=[canary.canary_id],
                        target_canary_texts=[canary.text],
                        allowed_doc_ids=allowed_doc_ids,
                        forbidden_doc_ids=forbidden_doc_ids,
                        leakage_checks=_leakage_checks(forbidden_doc_ids, docs),
                        reason_codes=["ALLOWED_QUERY_GENERATED", "EXACT_CANARY_CHECK_CONFIGURED"],
                    )
                )
            elif access == "FORBIDDEN" and doc.canaries:
                query = forbidden_query(doc, len(forbidden_candidates))
                if _query_has_forbidden_canary(query, doc) and not config["generation"].get("allow_forbidden_token_in_query", False):
                    query = f"Summarize the restricted {doc.collection or 'content'} document."
                forbidden_candidates.append(
                    CanaryTestCase(
                        test_case_id="pending",
                        user_id=user.user_id,
                        query=query,
                        expected_result="FORBIDDEN",
                        target_doc_id=doc.doc_id,
                        target_canary_ids=[canary.canary_id for canary in doc.canaries],
                        target_canary_texts=[canary.text for canary in doc.canaries],
                        allowed_doc_ids=allowed_doc_ids,
                        forbidden_doc_ids=forbidden_doc_ids,
                        leakage_checks=_leakage_checks(forbidden_doc_ids, docs),
                        reason_codes=["FORBIDDEN_QUERY_GENERATED", "FORBIDDEN_TOKEN_OMITTED_FROM_QUERY", "EXACT_CANARY_CHECK_CONFIGURED"],
                    )
                )
    allowed_selected = _balanced_take(allowed_candidates, target_allowed)
    forbidden_selected = _balanced_take(forbidden_candidates, target_forbidden)
    warnings: list[str] = []
    if len(allowed_selected) < target_allowed or len(forbidden_selected) < target_forbidden:
        warnings.append("INSUFFICIENT_CANARY_COVERAGE")
        if strict:
            raise ValueError("INSUFFICIENT_CANARY_COVERAGE")
    cases = _assign_ids(_interleave(allowed_selected, forbidden_selected))
    if strict:
        if not allowed_selected:
            raise ValueError("NO_ALLOWED_TEST_CASES")
        if not forbidden_selected:
            raise ValueError("NO_FORBIDDEN_TEST_CASES")
        for case in cases:
            if case.expected_result == "FORBIDDEN" and not _has_forbidden_evidence(case):
                raise ValueError("INSUFFICIENT_EVIDENCE")
    return CanaryPack(
        pack_id=f"{content.content_set_id}_pack",
        generated_at=now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        content_set_id=content.content_set_id,
        users=[user.user_id for user in sorted(users.users, key=lambda item: item.user_id)],
        test_users=sorted(users.users, key=lambda item: item.user_id),
        test_cases=cases,
        warnings=warnings,
    )


def write_pack(path: str | Path, pack: CanaryPack) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(yaml.safe_dump(pack.model_dump(), sort_keys=False), encoding="utf-8")


def load_pack(path: str | Path) -> CanaryPack:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return CanaryPack.model_validate(payload)


def write_queries_csv(path: str | Path, pack: CanaryPack) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANARY_QUERY_COLUMNS)
        writer.writeheader()
        for case in pack.test_cases:
            writer.writerow(
                {
                    "test_case_id": case.test_case_id,
                    "user_id": case.user_id,
                    "expected_result": case.expected_result,
                    "target_doc_id": case.target_doc_id,
                    "target_canary_ids": "|".join(case.target_canary_ids),
                    "query": case.query,
                    "allowed_doc_ids": "|".join(case.allowed_doc_ids),
                    "forbidden_doc_ids": "|".join(case.forbidden_doc_ids),
                    "forbidden_canary_count": len(case.leakage_checks.forbidden_canary_texts),
                    "forbidden_title_count": len(case.leakage_checks.forbidden_doc_titles),
                    "forbidden_metadata_count": len(case.leakage_checks.forbidden_metadata_values),
                    "reason_codes": "|".join(case.reason_codes),
                }
            )


def _leakage_checks(forbidden_doc_ids: list[str], docs: list[Document]) -> LeakageCheck:
    forbidden_docs = [doc for doc in docs if doc.doc_id in forbidden_doc_ids]
    metadata_values: list[str] = []
    for doc in forbidden_docs:
        metadata_values.extend(str(value) for value in doc.metadata.values() if value)
        if doc.sensitivity:
            metadata_values.append(doc.sensitivity)
        if doc.collection:
            metadata_values.append(doc.collection)
    return LeakageCheck(
        forbidden_canary_texts=_unique([canary.text for doc in forbidden_docs for canary in doc.canaries]),
        forbidden_doc_titles=_unique([doc.title for doc in forbidden_docs]),
        forbidden_metadata_values=_unique(metadata_values),
        forbidden_phrases=_unique([line.strip() for doc in forbidden_docs for line in doc.body.splitlines() if "CANARY_" in line]),
    )


def _balanced_take(cases: list[CanaryTestCase], limit: int) -> list[CanaryTestCase]:
    selected: list[CanaryTestCase] = []
    by_user: dict[str, list[CanaryTestCase]] = {}
    for case in cases:
        by_user.setdefault(case.user_id, []).append(case)
    while len(selected) < limit:
        progressed = False
        for user_id in sorted(by_user):
            if by_user[user_id] and len(selected) < limit:
                selected.append(by_user[user_id].pop(0))
                progressed = True
        if not progressed:
            break
    return selected


def _interleave(allowed: list[CanaryTestCase], forbidden: list[CanaryTestCase]) -> list[CanaryTestCase]:
    result: list[CanaryTestCase] = []
    for idx in range(max(len(allowed), len(forbidden))):
        if idx < len(allowed):
            result.append(allowed[idx])
        if idx < len(forbidden):
            result.append(forbidden[idx])
    return result


def _assign_ids(cases: list[CanaryTestCase]) -> list[CanaryTestCase]:
    return [case.model_copy(update={"test_case_id": f"tc_{idx:03d}"}) for idx, case in enumerate(cases, start=1)]


def _query_has_forbidden_canary(query: str, doc: Document) -> bool:
    return any(canary.text in query for canary in doc.canaries)


def _has_forbidden_evidence(case: CanaryTestCase) -> bool:
    checks = case.leakage_checks
    return bool(checks.forbidden_canary_texts or checks.forbidden_doc_titles or checks.forbidden_metadata_values or case.forbidden_doc_ids)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
