from __future__ import annotations

import pytest
import yaml

from inference_placement_bench.workload_profile import load_workload_profile


def test_parses_valid_workload_profile(project_root):
    workload = load_workload_profile(str(project_root / "examples/workloads/chat_support.yml"))
    assert workload.workload_id == "chat_support"
    assert workload.workload_type == "chat_text"


def test_fails_invalid_workload_profile(tmp_path):
    path = tmp_path / "bad.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "workload_id": "bad",
                "workload_type": "chat_text",
                "model": {"declared_model_name": "generic-model"},
                "benchmark": {"measured_requests": 0, "synthetic_prompt_count": 1},
                "request": {"path": "/infer"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_workload_profile(str(path))
