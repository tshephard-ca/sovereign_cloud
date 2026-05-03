import pytest

from rag_permission_canary.users import load_users


def test_parses_valid_test_users(write_yaml, base_users):
    users = load_users(write_yaml("users.yml", base_users))
    assert {user.user_id for user in users.users} == {"user_hr", "user_fin"}


def test_fails_fewer_than_two_users_in_strict_mode(write_yaml, base_users):
    base_users["users"] = base_users["users"][:1]
    with pytest.raises(ValueError, match="LESS_THAN_TWO_TEST_USERS"):
        load_users(write_yaml("users.yml", base_users), strict=True)
