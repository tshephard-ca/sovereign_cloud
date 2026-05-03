from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml

from rag_permission_canary.canary_generate import generate_canary_pack
from rag_permission_canary.config import load_config
from rag_permission_canary.content_set import load_content_set
from rag_permission_canary.endpoint_profile import load_endpoint_profile
from rag_permission_canary.permissions import load_permissions
from rag_permission_canary.users import load_users


@pytest.fixture
def write_yaml(tmp_path):
    def _write(name: str, payload: object) -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def base_content():
    return {
        "content_set_id": "test_content",
        "content_set_version": 1,
        "documents": [
            {
                "doc_id": "doc_hr",
                "title": "HR Plan",
                "collection": "hr",
                "sensitivity": "internal",
                "metadata": {"department": "hr", "record_type": "benefits"},
                "body": "Allowed HR body CANARY_HR_ALPHA HR-CODE-1",
                "canaries": [{"canary_id": "c_hr", "text": "CANARY_HR_ALPHA"}, {"canary_id": "c_hr_code", "text": "HR-CODE-1"}],
            },
            {
                "doc_id": "doc_fin",
                "title": "Finance Draft",
                "collection": "finance",
                "sensitivity": "restricted",
                "metadata": {"department": "finance", "record_type": "forecast"},
                "body": "Finance body CANARY_FIN_BRAVO FIN-CODE-2",
                "canaries": [{"canary_id": "c_fin", "text": "CANARY_FIN_BRAVO"}, {"canary_id": "c_fin_code", "text": "FIN-CODE-2"}],
            },
            {
                "doc_id": "doc_pub",
                "title": "Public FAQ",
                "collection": "public",
                "sensitivity": "public",
                "metadata": {"department": "product", "record_type": "faq"},
                "body": "Public body CANARY_PUBLIC_CHARLIE",
                "canaries": [{"canary_id": "c_pub", "text": "CANARY_PUBLIC_CHARLIE"}],
            },
        ],
    }


@pytest.fixture
def big_content():
    docs = []
    for idx in range(1, 11):
        collection = "left" if idx <= 5 else "right"
        docs.append(
            {
                "doc_id": f"doc_{idx:02d}",
                "title": f"Doc {idx:02d}",
                "collection": collection,
                "metadata": {"department": collection, "record_type": f"type{idx}"},
                "body": f"Body {idx} CANARY_DOC_{idx:02d}",
                "canaries": [{"canary_id": f"c_{idx:02d}", "text": f"CANARY_DOC_{idx:02d}"}],
            }
        )
    return {"content_set_id": "big_content", "documents": docs}


@pytest.fixture
def base_users():
    return {
        "users": [
            {"user_id": "user_hr", "auth": {"type": "bearer_env", "token_env": "TOKEN_HR"}, "groups": ["hr_readers", "public_readers"]},
            {"user_id": "user_fin", "auth": {"type": "bearer_env", "token_env": "TOKEN_FIN"}, "groups": ["finance_readers", "public_readers"]},
        ]
    }


@pytest.fixture
def big_users():
    return {
        "users": [
            {"user_id": "user_left", "auth": {"type": "none"}, "groups": ["left_readers"]},
            {"user_id": "user_right", "auth": {"type": "none"}, "groups": ["right_readers"]},
        ]
    }


@pytest.fixture
def base_permissions():
    return {
        "permission_model": "group_acl",
        "default_access": "deny",
        "grants": [
            {"subject_type": "group", "subject": "public_readers", "access": "allow", "documents": ["doc_pub"]},
            {"subject_type": "group", "subject": "hr_readers", "access": "allow", "collections": ["hr"]},
            {"subject_type": "group", "subject": "finance_readers", "access": "allow", "collections": ["finance"]},
        ],
        "denies": [
            {"subject_type": "group", "subject": "hr_readers", "access": "deny", "collections": ["finance"]},
            {"subject_type": "group", "subject": "finance_readers", "access": "deny", "collections": ["hr"]},
        ],
    }


@pytest.fixture
def big_permissions():
    return {
        "permission_model": "group_acl",
        "default_access": "deny",
        "grants": [
            {"subject_type": "group", "subject": "left_readers", "access": "allow", "collections": ["left"]},
            {"subject_type": "group", "subject": "right_readers", "access": "allow", "collections": ["right"]},
        ],
        "denies": [
            {"subject_type": "group", "subject": "left_readers", "access": "deny", "collections": ["right"]},
            {"subject_type": "group", "subject": "right_readers", "access": "deny", "collections": ["left"]},
        ],
    }


@pytest.fixture
def endpoint_payload():
    return {
        "endpoint_id": "endpoint_under_test",
        "base_url": "https://rag-endpoint.example.invalid",
        "request": {
            "method": "POST",
            "path": "/query",
            "headers": {"Content-Type": "application/json"},
            "body_template": {"query": "{{query}}", "user_id": "{{user_id}}", "test_case_id": "{{test_case_id}}"},
        },
        "auth": {"user_auth_from_test_user": True},
        "response_extractors": {
            "answer_text_json_path": "$.answer",
            "citations_json_path": "$.citations",
            "citation_doc_id_json_path": "$.doc_id",
            "citation_title_json_path": "$.title",
            "citation_snippet_json_path": "$.snippet",
            "metadata_json_path": "$.metadata",
            "raw_context_json_path": "$.retrieved_context",
        },
    }


@pytest.fixture
def generated_pack(tmp_path, write_yaml, big_content, big_users, big_permissions):
    content_path = write_yaml("content.yml", big_content)
    users_path = write_yaml("users.yml", big_users)
    perms_path = write_yaml("permissions.yml", big_permissions)
    pack = generate_canary_pack(
        content=load_content_set(content_path),
        users=load_users(users_path),
        permissions=load_permissions(perms_path),
        config=load_config(None),
        now="2026-01-01T00:00:00Z",
    )
    return pack, content_path


def mock_transport(payload: dict, status_code: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)
