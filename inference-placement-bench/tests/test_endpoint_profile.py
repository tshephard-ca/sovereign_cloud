from __future__ import annotations

import pytest
import yaml

from inference_placement_bench.endpoint_profile import load_endpoint_profiles


def test_parses_valid_endpoint_profile(project_root):
    endpoints = load_endpoint_profiles(str(project_root / "examples/endpoints.yml"))
    assert [endpoint.endpoint_id for endpoint in endpoints.endpoints] == ["endpoint_a", "endpoint_b"]


def test_fails_duplicate_endpoint_id(tmp_path):
    path = tmp_path / "endpoints.yml"
    payload = {
        "endpoints": [
            {"endpoint_id": "duplicate", "base_url": "https://a.example.invalid"},
            {"endpoint_id": "duplicate", "base_url": "https://b.example.invalid"},
        ]
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(Exception):
        load_endpoint_profiles(str(path))
