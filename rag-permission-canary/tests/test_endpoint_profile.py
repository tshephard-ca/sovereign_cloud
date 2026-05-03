import pytest

from rag_permission_canary.canary_generate import generate_canary_pack
from rag_permission_canary.config import load_config
from rag_permission_canary.content_set import load_content_set
from rag_permission_canary.endpoint_profile import load_endpoint_profile, render_body_template
from rag_permission_canary.permissions import load_permissions
from rag_permission_canary.users import load_users


def test_validates_endpoint_yml(write_yaml, endpoint_payload):
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    assert endpoint.endpoint_id == "endpoint_under_test"


def test_fails_unsafe_non_https_endpoint_unless_local(write_yaml, endpoint_payload):
    endpoint_payload["base_url"] = "http://example.invalid"
    endpoint_payload["local_test_only"] = False
    with pytest.raises(ValueError, match="HTTPS_REQUIRED"):
        load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))


def test_allows_local_test_http_endpoint(write_yaml, endpoint_payload):
    endpoint_payload["base_url"] = "http://localhost:8080"
    endpoint_payload["local_test_only"] = True
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    assert endpoint.local_test_only is True


def test_payload_template_replaces_query_and_user_id(write_yaml, endpoint_payload, base_content, base_users, base_permissions):
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    pack = generate_canary_pack(
        content=load_content_set(write_yaml("content.yml", base_content)),
        users=load_users(write_yaml("users.yml", base_users)),
        permissions=load_permissions(write_yaml("permissions.yml", base_permissions)),
        config=load_config(None),
    )
    case = pack.test_cases[0]
    user = pack.test_users[0]
    body = render_body_template(endpoint, case, user)
    assert body["query"] == case.query
    assert body["user_id"] == user.user_id


def test_payload_template_fails_unknown_placeholder(write_yaml, endpoint_payload):
    endpoint_payload["request"]["body_template"]["bad"] = "{{unknown_value}}"
    with pytest.raises(ValueError, match="unknown endpoint template placeholder"):
        load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
