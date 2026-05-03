"""Permission YAML parsing and expected access calculation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml

from .models import Access, ContentSet, Document, PermissionModel, PermissionRule, TestUser


def load_permissions(path: str | Path) -> PermissionModel:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    model = PermissionModel.model_validate(payload)
    if model.permission_model == "attribute_acl":
        # Parsed for visibility; not evaluated by the MVP.
        pass
    return model


def expected_access(user: TestUser, doc: Document, permissions: PermissionModel, config: dict | None = None) -> Access:
    if permissions.permission_model == "attribute_acl":
        return "UNKNOWN"
    config = config or {}
    user_rule_precedence = bool(config.get("user_rule_precedence", False))
    grant_matches = [rule for rule in permissions.grants if _rule_matches(rule, user, doc)]
    deny_matches = [rule for rule in permissions.denies if _rule_matches(rule, user, doc)]
    if user_rule_precedence:
        user_denies = [rule for rule in deny_matches if rule.subject_type == "user"]
        user_grants = [rule for rule in grant_matches if rule.subject_type == "user"]
        if user_denies:
            return "FORBIDDEN"
        if user_grants:
            return "ALLOWED"
    if deny_matches:
        return "FORBIDDEN"
    if grant_matches:
        return "ALLOWED"
    return "ALLOWED" if permissions.default_access == "allow" else "FORBIDDEN"


def access_matrix(users: list[TestUser], content: ContentSet, permissions: PermissionModel, config: dict | None = None) -> dict[tuple[str, str], Access]:
    return {
        (user.user_id, doc.doc_id): expected_access(user, doc, permissions, config)
        for user in users
        for doc in content.documents
    }


def _rule_matches(rule: PermissionRule, user: TestUser, doc: Document) -> bool:
    if rule.subject_type == "user" and rule.subject != user.user_id:
        return False
    if rule.subject_type == "group" and rule.subject not in user.groups:
        return False
    if rule.subject_type == "attribute":
        return False
    target_doc = bool(rule.documents and doc.doc_id in rule.documents)
    target_collection = bool(rule.collections and doc.collection in rule.collections)
    target_metadata = bool(rule.metadata and all(doc.metadata.get(key) == value for key, value in rule.metadata.items()))
    if not rule.documents and not rule.collections and not rule.metadata:
        return True
    return target_doc or target_collection or target_metadata


def validate_permissions_have_coverage(users: list[TestUser], content: ContentSet, permissions: PermissionModel, config: dict | None = None) -> tuple[int, int]:
    matrix = access_matrix(users, content, permissions, config)
    allowed = sum(1 for value in matrix.values() if value == "ALLOWED")
    forbidden = sum(1 for value in matrix.values() if value == "FORBIDDEN")
    return allowed, forbidden
