import csv
import json

import pytest

from rag_permission_canary.canary_generate import generate_canary_pack, write_queries_csv
from rag_permission_canary.config import load_config
from rag_permission_canary.content_set import load_content_set
from rag_permission_canary.evidence import CANARY_QUERY_COLUMNS
from rag_permission_canary.permissions import load_permissions
from rag_permission_canary.users import load_users


def test_generates_exactly_20_when_coverage_permits(write_yaml, big_content, big_users, big_permissions):
    pack = generate_canary_pack(
        content=load_content_set(write_yaml("content.yml", big_content)),
        users=load_users(write_yaml("users.yml", big_users)),
        permissions=load_permissions(write_yaml("permissions.yml", big_permissions)),
        config=load_config(None),
        now="2026-01-01T00:00:00Z",
    )
    assert len(pack.test_cases) == 20
    assert sum(case.expected_result == "ALLOWED" for case in pack.test_cases) == 10
    assert sum(case.expected_result == "FORBIDDEN" for case in pack.test_cases) == 10


def test_balances_users_where_possible(generated_pack):
    pack, _ = generated_pack
    counts = {user: sum(case.user_id == user for case in pack.test_cases) for user in pack.users}
    assert set(counts.values()) == {10}


def test_avoids_forbidden_canary_text_in_forbidden_query_by_default(generated_pack):
    pack, _ = generated_pack
    for case in pack.test_cases:
        if case.expected_result == "FORBIDDEN":
            assert not any(text in case.query for text in case.leakage_checks.forbidden_canary_texts)


def test_includes_allowed_canary_text_in_allowed_query_when_useful(generated_pack):
    pack, _ = generated_pack
    allowed = [case for case in pack.test_cases if case.expected_result == "ALLOWED"]
    assert any("CANARY_DOC_" in case.query for case in allowed)


def test_writes_canary_queries_csv_with_exact_column_order(tmp_path, generated_pack):
    pack, _ = generated_pack
    output = tmp_path / "queries.csv"
    write_queries_csv(output, pack)
    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        assert next(reader) == CANARY_QUERY_COLUMNS


def test_strict_mode_fails_if_no_forbidden_tests(write_yaml, big_content, big_users):
    perms = {"permission_model": "group_acl", "default_access": "allow"}
    with pytest.raises(ValueError, match="INSUFFICIENT_CANARY_COVERAGE"):
        generate_canary_pack(
            content=load_content_set(write_yaml("content.yml", big_content)),
            users=load_users(write_yaml("users.yml", big_users)),
            permissions=load_permissions(write_yaml("permissions.yml", perms)),
            config=load_config(None),
            strict=True,
        )


def test_output_ordering_is_deterministic(write_yaml, big_content, big_users, big_permissions):
    kwargs = {
        "content": load_content_set(write_yaml("content.yml", big_content)),
        "users": load_users(write_yaml("users.yml", big_users)),
        "permissions": load_permissions(write_yaml("permissions.yml", big_permissions)),
        "config": load_config(None),
        "now": "2026-01-01T00:00:00Z",
    }
    first = generate_canary_pack(**kwargs)
    second = generate_canary_pack(**kwargs)
    assert [case.model_dump() for case in first.test_cases] == [case.model_dump() for case in second.test_cases]
