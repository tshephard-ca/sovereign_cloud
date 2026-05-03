from __future__ import annotations

from brownout_policy_compiler.compile_rules import compile_from_paths
from brownout_policy_compiler.policy_pack import load_policy_pack

from .conftest import write_yaml


def test_default_policy_pack_is_used_when_none_supplied():
    pack, result, supplied = load_policy_pack(None)
    assert pack.pack_id == "default"
    assert not supplied
    assert "POLICY_PACK_NOT_SUPPLIED_USING_DEFAULT" in result.warnings


def test_user_policy_pack_overrides_ttl_defaults(tmp_path, compile_options_factory):
    pack_path = write_yaml(
        tmp_path / "pack.yml",
        {
            "pack_id": "short",
            "ttl": {
                "default_minutes": 5,
                "p0_max_minutes": 5,
                "p1_max_minutes": 5,
                "p2_max_minutes": 5,
                "p3_max_minutes": 5,
                "p4_max_minutes": 5,
                "null_route_max_minutes": 5,
            },
        },
    )
    result = compile_from_paths(compile_options_factory(policy_pack_path=pack_path))
    assert {action.ttl_minutes for action in result.plan.actions} == {5}


def test_invalid_policy_pack_fails_validation(tmp_path):
    path = write_yaml(tmp_path / "bad_pack.yml", {"description": "missing pack id"})
    pack, result, supplied = load_policy_pack(path)
    assert supplied
    assert pack is None
    assert "POLICY_PACK_INVALID" in result.blockers

