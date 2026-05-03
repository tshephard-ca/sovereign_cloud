"""Cross-file validation helpers."""

from __future__ import annotations

from pathlib import Path

from .config import load_config
from .content_set import load_content_set
from .endpoint_profile import load_endpoint_profile
from .permissions import load_permissions, validate_permissions_have_coverage
from .users import load_users


def validate_inputs(
    *,
    content_path: str | Path,
    users_path: str | Path,
    permissions_path: str | Path,
    endpoint_path: str | Path,
    config_path: str | Path | None = None,
    strict: bool = False,
) -> dict[str, object]:
    config = load_config(config_path)
    content = load_content_set(content_path, strict=strict)
    users = load_users(users_path, strict=strict)
    permissions = load_permissions(permissions_path)
    endpoint = load_endpoint_profile(endpoint_path, strict=strict)
    allowed, forbidden = validate_permissions_have_coverage(users.users, content, permissions, config)
    blockers: list[str] = []
    warnings: list[str] = []
    if allowed == 0:
        blockers.append("NO_ALLOWED_TEST_CASES")
    if forbidden == 0:
        blockers.append("NO_FORBIDDEN_TEST_CASES")
    if permissions.permission_model == "attribute_acl":
        warnings.append("ATTRIBUTE_ACL_NOT_IMPLEMENTED")
    if strict and blockers:
        raise ValueError("|".join(blockers))
    return {
        "valid": not blockers,
        "content_set_id": content.content_set_id,
        "users": len(users.users),
        "documents": len(content.documents),
        "allowed_user_doc_pairs": allowed,
        "forbidden_user_doc_pairs": forbidden,
        "endpoint_id": endpoint.endpoint_id,
        "warnings": warnings,
        "blockers": blockers,
        "reason_codes": ["CONTENT_SET_VALID", "USERS_VALID", "PERMISSIONS_VALID"],
    }
