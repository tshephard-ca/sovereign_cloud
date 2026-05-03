"""Test-user YAML parsing and auth helpers."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import TestUser, TestUsers, UserAuth


def load_users(path: str | Path, *, strict: bool = False) -> TestUsers:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    users = TestUsers.model_validate(payload)
    validate_users(users, strict=strict)
    return users


def validate_users(users: TestUsers, *, strict: bool = False) -> None:
    if strict and len(users.users) < 2:
        raise ValueError("LESS_THAN_TWO_TEST_USERS")
    ids = [user.user_id for user in users.users]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate user_id in test users")
    for user in users.users:
        if user.auth.type in {"bearer_env", "header_env"}:
            env_name = user.auth.token_env or user.auth.header_value_env
            if not env_name and strict:
                raise ValueError(f"auth env name missing for {user.user_id}")


def user_by_id(users: TestUsers) -> dict[str, TestUser]:
    return {user.user_id: user for user in users.users}


def auth_headers_for_user(user: TestUser, *, strict: bool = False) -> tuple[dict[str, str], list[str], list[str]]:
    warnings: list[str] = []
    reason_codes: list[str] = []
    auth = user.auth
    if auth.type == "none":
        return {}, warnings, reason_codes
    env_name = auth.token_env or auth.header_value_env
    token = os.environ.get(env_name, "") if env_name else ""
    if not token:
        if strict:
            raise ValueError(f"AUTH_ENV_MISSING:{env_name}")
        warnings.append("TEST_USER_AUTH_MISSING")
        reason_codes.append("TEST_USER_AUTH_MISSING")
        return {}, warnings, reason_codes
    reason_codes.append("TEST_USER_AUTH_PRESENT")
    if auth.type == "bearer_env":
        return {"Authorization": f"Bearer {token}"}, warnings, reason_codes
    return {auth.header_name: token}, warnings, reason_codes
