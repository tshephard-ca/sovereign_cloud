"""Expected access and tested-boundary output tables."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .models import CanaryPack, ContentSet, PermissionModel, RunResults, TestUsers
from .permissions import expected_access


ACCESS_MATRIX_COLUMNS = [
    "user_id",
    "doc_id",
    "collection",
    "expected_access",
    "test_case_count",
    "tested_as_allowed",
    "tested_as_forbidden",
    "leak_found",
    "allowed_evidence_found",
]

BOUNDARY_COVERAGE_COLUMNS = [
    "boundary_id",
    "user_id",
    "collection",
    "allowed_docs",
    "forbidden_docs",
    "allowed_tests",
    "forbidden_tests",
    "leak_count",
    "review_count",
    "status",
]


def build_access_matrix(
    content: ContentSet,
    users: TestUsers,
    permissions: PermissionModel,
    config: dict | None = None,
    pack: CanaryPack | None = None,
    results: RunResults | None = None,
) -> list[dict[str, object]]:
    test_counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"ALLOWED": 0, "FORBIDDEN": 0})
    if pack:
        for case in pack.test_cases:
            test_counts[(case.user_id, case.target_doc_id)][case.expected_result] += 1
    leak_pairs = {
        (result.user_id, result.target_doc_id)
        for result in (results.test_results if results else [])
        if result.status == "FAIL" and result.target_doc_id
    }
    allowed_evidence_pairs = {
        (result.user_id, result.target_doc_id)
        for result in (results.test_results if results else [])
        if result.expected_result == "ALLOWED" and result.status == "PASS" and result.target_doc_id
    }
    rows: list[dict[str, object]] = []
    for user in sorted(users.users, key=lambda item: item.user_id):
        for doc in sorted(content.documents, key=lambda item: item.doc_id):
            counts = test_counts[(user.user_id, doc.doc_id)]
            rows.append(
                {
                    "user_id": user.user_id,
                    "doc_id": doc.doc_id,
                    "collection": doc.collection,
                    "expected_access": expected_access(user, doc, permissions, config),
                    "test_case_count": counts["ALLOWED"] + counts["FORBIDDEN"],
                    "tested_as_allowed": counts["ALLOWED"] > 0,
                    "tested_as_forbidden": counts["FORBIDDEN"] > 0,
                    "leak_found": (user.user_id, doc.doc_id) in leak_pairs,
                    "allowed_evidence_found": (user.user_id, doc.doc_id) in allowed_evidence_pairs,
                }
            )
    return rows


def build_boundary_coverage(access_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in access_rows:
        grouped[(str(row["user_id"]), str(row["collection"]))].append(row)
    output: list[dict[str, object]] = []
    for (user_id, collection), rows in sorted(grouped.items()):
        allowed_docs = [row for row in rows if row["expected_access"] == "ALLOWED"]
        forbidden_docs = [row for row in rows if row["expected_access"] == "FORBIDDEN"]
        leak_count = sum(bool(row["leak_found"]) for row in rows)
        review_count = sum((row["expected_access"] == "ALLOWED" and row["tested_as_allowed"] and not row["allowed_evidence_found"]) for row in rows)
        if leak_count:
            status = "FAIL"
        elif review_count:
            status = "REVIEW"
        elif any(row["test_case_count"] for row in rows):
            status = "PASS"
        else:
            status = "UNTESTED"
        output.append(
            {
                "boundary_id": f"{user_id}:{collection}",
                "user_id": user_id,
                "collection": collection,
                "allowed_docs": len(allowed_docs),
                "forbidden_docs": len(forbidden_docs),
                "allowed_tests": sum(int(row["tested_as_allowed"]) for row in rows),
                "forbidden_tests": sum(int(row["tested_as_forbidden"]) for row in rows),
                "leak_count": leak_count,
                "review_count": review_count,
                "status": status,
            }
        )
    return output


def write_access_matrix_csv(path: str | Path, rows: list[dict[str, object]]) -> None:
    _write_csv(path, ACCESS_MATRIX_COLUMNS, rows)


def write_boundary_coverage_csv(path: str | Path, rows: list[dict[str, object]]) -> None:
    _write_csv(path, BOUNDARY_COVERAGE_COLUMNS, rows)


def _write_csv(path: str | Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
