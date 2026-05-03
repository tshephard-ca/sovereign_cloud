from rag_permission_canary.content_set import load_content_set
from rag_permission_canary.permissions import expected_access, load_permissions
from rag_permission_canary.users import load_users


def test_parses_group_acl_permissions(write_yaml, base_permissions):
    permissions = load_permissions(write_yaml("permissions.yml", base_permissions))
    assert permissions.permission_model == "group_acl"


def test_parses_user_acl_permissions(write_yaml):
    permissions = load_permissions(
        write_yaml(
            "permissions.yml",
            {
                "permission_model": "user_acl",
                "default_access": "deny",
                "grants": [{"subject_type": "user", "subject": "u1", "access": "allow", "documents": ["d1"]}],
            },
        )
    )
    assert permissions.permission_model == "user_acl"


def test_deny_overrides_allow(write_yaml, base_content, base_users, base_permissions):
    content = load_content_set(write_yaml("content.yml", base_content))
    users = load_users(write_yaml("users.yml", base_users))
    permissions = load_permissions(write_yaml("permissions.yml", base_permissions))
    user_hr = next(user for user in users.users if user.user_id == "user_hr")
    doc_fin = next(doc for doc in content.documents if doc.doc_id == "doc_fin")
    assert expected_access(user_hr, doc_fin, permissions) == "FORBIDDEN"


def test_computes_expected_allowed_and_forbidden(write_yaml, base_content, base_users, base_permissions):
    content = load_content_set(write_yaml("content.yml", base_content))
    users = load_users(write_yaml("users.yml", base_users))
    permissions = load_permissions(write_yaml("permissions.yml", base_permissions))
    user_hr = next(user for user in users.users if user.user_id == "user_hr")
    doc_hr = next(doc for doc in content.documents if doc.doc_id == "doc_hr")
    doc_fin = next(doc for doc in content.documents if doc.doc_id == "doc_fin")
    assert expected_access(user_hr, doc_hr, permissions) == "ALLOWED"
    assert expected_access(user_hr, doc_fin, permissions) == "FORBIDDEN"


def test_unknown_for_attribute_acl(write_yaml, base_content, base_users):
    content = load_content_set(write_yaml("content.yml", base_content))
    users = load_users(write_yaml("users.yml", base_users))
    permissions = load_permissions(write_yaml("permissions.yml", {"permission_model": "attribute_acl", "default_access": "deny"}))
    assert expected_access(users.users[0], content.documents[0], permissions) == "UNKNOWN"
