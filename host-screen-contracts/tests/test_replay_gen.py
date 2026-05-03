from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from host_screen_contracts.contract_model import contract_to_dict
from host_screen_contracts.replay_gen import generate_pytest


def test_generated_pytest_file_imports_and_runs_against_trace_replay_driver(tmp_path, order_result):
    result = order_result()
    contract_path = tmp_path / "contract.yml"
    contract_path.write_text(yaml.safe_dump(contract_to_dict(result.contract), sort_keys=False))
    test_path = tmp_path / "test_generated_replay.py"
    test_path.write_text(generate_pytest(Path("examples/order_lookup.trace.jsonl"), contract_path, result.replay_case))
    assert "TraceReplayDriver" in test_path.read_text()
    assert pytest.main([str(test_path), "-q"]) == 0


def test_generated_pytest_can_load_external_replay_case(tmp_path, order_result):
    result = order_result()
    contract_path = tmp_path / "contract.yml"
    case_path = tmp_path / "case.yml"
    contract_path.write_text(yaml.safe_dump(contract_to_dict(result.contract), sort_keys=False))
    case_path.write_text(yaml.safe_dump(result.replay_case.model_dump(mode="json"), sort_keys=False))
    test_path = tmp_path / "test_generated_replay_external_case.py"
    test_path.write_text(
        generate_pytest(Path("examples/order_lookup.trace.jsonl"), contract_path, result.replay_case, case_path)
    )
    assert "CASE_PATH" in test_path.read_text()
    assert pytest.main([str(test_path), "-q"]) == 0
