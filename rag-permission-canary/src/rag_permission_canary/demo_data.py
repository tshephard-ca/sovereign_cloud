"""Generated enterprise-style demo fixtures."""

from __future__ import annotations

import random
import shutil
from pathlib import Path

import yaml

from .access_matrix import build_access_matrix, build_boundary_coverage, write_access_matrix_csv, write_boundary_coverage_csv
from .canary_generate import generate_canary_pack, write_pack, write_queries_csv
from .config import load_config
from .content_set import load_content_set
from .endpoint_profile import load_endpoint_profile
from .fixture_quality import assess_fixture, write_fixture_quality_json, write_fixture_quality_markdown
from .permissions import load_permissions
from .users import load_users


COLLECTIONS = ["hr", "finance", "legal", "engineering", "public"]
ROLE_COLLECTIONS = ["hr", "finance", "legal", "engineering"]


def generate_demo_fixtures(
    output_dir: Path,
    users_count: int = 4,
    documents_count: int = 20,
    seed: int = 1,
    force: bool = False,
    now: str | None = None,
) -> dict[str, Path]:
    if output_dir.exists() and any(output_dir.iterdir()):
        if not force:
            raise ValueError(f"{output_dir} is not empty; use --force to replace generated demo fixtures")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    content_path = output_dir / "content_set.yml"
    users_path = output_dir / "test_users.yml"
    permissions_path = output_dir / "permissions.yml"
    endpoint_path = output_dir / "endpoint.yml"
    config_path = output_dir / "thresholds.yml"
    pack_path = output_dir / "canary_pack.yml"
    queries_path = output_dir / "canary_queries.csv"
    access_matrix_path = output_dir / "access_matrix.csv"
    boundary_coverage_path = output_dir / "boundary_coverage.csv"
    quality_json_path = output_dir / "fixture_quality.json"
    quality_md_path = output_dir / "fixture_quality.md"
    _write_yaml(content_path, _content_payload(max(documents_count, 8), rng))
    _write_yaml(users_path, _users_payload(max(users_count, 2)))
    _write_yaml(permissions_path, _permissions_payload(max(users_count, 2)))
    _write_yaml(endpoint_path, _endpoint_payload())
    _write_yaml(config_path, _config_payload())
    config = load_config(config_path)
    content = load_content_set(content_path)
    users = load_users(users_path)
    permissions = load_permissions(permissions_path)
    endpoint = load_endpoint_profile(endpoint_path)
    pack = generate_canary_pack(content=content, users=users, permissions=permissions, config=config, now=now)
    write_pack(pack_path, pack)
    write_queries_csv(queries_path, pack)
    access_rows = build_access_matrix(content, users, permissions, config, pack)
    boundary_rows = build_boundary_coverage(access_rows)
    write_access_matrix_csv(access_matrix_path, access_rows)
    write_boundary_coverage_csv(boundary_coverage_path, boundary_rows)
    quality = assess_fixture(content, users, permissions, endpoint, config, pack)
    write_fixture_quality_json(quality_json_path, quality)
    write_fixture_quality_markdown(quality_md_path, quality)
    return {
        "content": content_path,
        "users": users_path,
        "permissions": permissions_path,
        "endpoint": endpoint_path,
        "config": config_path,
        "pack": pack_path,
        "queries": queries_path,
        "access_matrix": access_matrix_path,
        "boundary_coverage": boundary_coverage_path,
        "fixture_quality_json": quality_json_path,
        "fixture_quality_markdown": quality_md_path,
    }


def _content_payload(documents_count: int, rng: random.Random) -> dict[str, object]:
    documents = []
    for index in range(1, documents_count + 1):
        collection = COLLECTIONS[(index - 1) % len(COLLECTIONS)]
        sensitivity = "public" if collection == "public" else "restricted"
        marker = f"MARKER_{collection.upper()}_{index:03d}_{rng.randrange(16**6):06X}"
        canary = f"CANARY_{collection.upper()}_{index:03d}_{rng.randrange(16**6):06X}"
        title = f"{collection.title()} Boundary Record {index:03d}"
        documents.append(
            {
                "doc_id": f"doc_{collection}_{index:03d}",
                "title": title,
                "collection": collection,
                "sensitivity": sensitivity,
                "metadata": {
                    "department": collection,
                    "record_type": f"{collection}_boundary_record",
                    "permission_marker": marker,
                    "case_marker": f"CASE_{index:03d}_{rng.randrange(16**4):04X}",
                },
                "body": (
                    f"{title} is synthetic permission-regression evidence. "
                    f"It contains exact canary {canary} and metadata marker {marker}. "
                    f"This text is not production confidential information."
                ),
                "canaries": [{"canary_id": f"canary_{collection}_{index:03d}", "text": canary, "description": "Synthetic exact permission canary."}],
            }
        )
    return {
        "content_set_id": "generated_enterprise_permission_boundary",
        "content_set_version": 1,
        "description": "Synthetic enterprise-style permission boundary fixture with unique canary and metadata markers.",
        "documents": documents,
    }


def _users_payload(users_count: int) -> dict[str, object]:
    roles = ROLE_COLLECTIONS[: max(2, min(users_count, len(ROLE_COLLECTIONS)))]
    users = [
        {
            "user_id": f"user_{role}",
            "display_name": f"{role.title()} Test User",
            "auth": {"type": "none"},
            "groups": [f"{role}_readers", "public_readers"],
            "attributes": {"department": role},
        }
        for role in roles
    ]
    return {"users": users}


def _permissions_payload(users_count: int) -> dict[str, object]:
    roles = ROLE_COLLECTIONS[: max(2, min(users_count, len(ROLE_COLLECTIONS)))]
    grants = [{"subject_type": "group", "subject": "public_readers", "access": "allow", "collections": ["public"]}]
    denies = []
    for role in roles:
        grants.append({"subject_type": "group", "subject": f"{role}_readers", "access": "allow", "collections": [role]})
        for forbidden in ROLE_COLLECTIONS:
            if forbidden != role:
                denies.append({"subject_type": "group", "subject": f"{role}_readers", "access": "deny", "collections": [forbidden]})
    return {"permission_model": "group_acl", "default_access": "deny", "grants": grants, "denies": denies}


def _endpoint_payload() -> dict[str, object]:
    return {
        "endpoint_id": "local_demo_endpoint",
        "base_url": "http://127.0.0.1:8000",
        "local_test_only": True,
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


def _config_payload() -> dict[str, object]:
    return {
        "default_total_queries": 20,
        "required_allowed_queries": 10,
        "required_forbidden_queries": 10,
        "business_context": {
            "release_name": "demo-enterprise-rag-release",
            "owner": "ai-platform",
            "risk_domain": "cross_department_rag_permissions",
            "deployment_stage": "pre_launch",
            "decision_threshold": "fail_blocks_release",
        },
    }


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
