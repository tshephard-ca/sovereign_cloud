from __future__ import annotations

from pathlib import Path

import yaml

from .replay_model import ReplayCase


def generate_pytest(
    trace_path: str | Path,
    contract_path: str | Path,
    replay_case: ReplayCase,
    replay_case_path: str | Path | None = None,
) -> str:
    case_literal = yaml.safe_dump(replay_case.model_dump(mode="json"), sort_keys=False)
    if replay_case_path is not None:
        case_loader = f'CASE_PATH = Path({str(replay_case_path)!r})\n'
        case_body = '    case = yaml.safe_load(CASE_PATH.read_text())\n'
    else:
        case_loader = f'CASE_YAML = """\\\n{case_literal}"""\n'
        case_body = '    case = yaml.safe_load(CASE_YAML)\n'
    return f'''"""Generated replay test for a recorded terminal trace."""

from pathlib import Path

import yaml

from host_screen_contracts.contract_model import TransactionContract
from host_screen_contracts.parse_trace import load_trace
from host_screen_contracts.redact import REDACTED
from host_screen_contracts.replay_driver import TraceReplayDriver


TRACE_PATH = Path({str(trace_path)!r})
CONTRACT_PATH = Path({str(contract_path)!r})
{case_loader}


def test_recorded_trace_replay():
    events = load_trace(TRACE_PATH)
    contract = TransactionContract(**yaml.safe_load(CONTRACT_PATH.read_text()))
{case_body.rstrip()}
    driver = TraceReplayDriver(events, contract)

    assert driver.current_screen_hash() == case["start_screen_hash"]
    for step in case["steps"]:
        assert driver.current_screen_hash() == step["expect_screen_hash"]
        next_hash = driver.apply(step["aid"], step.get("inputs", {{}}))
        assert next_hash == step["expect_next_screen_hash"]

    response = driver.extract_response()
    for name, expected_value in case["expected_response"].items():
        if expected_value != REDACTED:
            assert response[name] == expected_value
    driver.assert_no_unexpected_transition()
'''


def generate_package_pytest(
    contract_path: str | Path,
    cases: list[tuple[str, str | Path, str | Path]],
) -> str:
    """Generate one pytest module that replays every case in a package."""
    case_entries = [
        {"case_id": case_id, "trace_path": str(trace_path), "case_path": str(case_path)}
        for case_id, trace_path, case_path in cases
    ]
    return f'''"""Generated replay tests for a recorded terminal trace package."""

from pathlib import Path

import pytest
import yaml

from host_screen_contracts.contract_model import TransactionContract
from host_screen_contracts.parse_trace import load_trace
from host_screen_contracts.redact import REDACTED
from host_screen_contracts.replay_driver import TraceReplayDriver


CONTRACT_PATH = Path({str(contract_path)!r})
CASES = {case_entries!r}


@pytest.mark.parametrize("case_info", CASES, ids=[case["case_id"] for case in CASES])
def test_recorded_package_trace_replay(case_info):
    events = load_trace(Path(case_info["trace_path"]))
    contract = TransactionContract(**yaml.safe_load(CONTRACT_PATH.read_text()))
    case = yaml.safe_load(Path(case_info["case_path"]).read_text())
    driver = TraceReplayDriver(events, contract)

    assert driver.current_screen_hash() == case["start_screen_hash"]
    for step in case["steps"]:
        assert driver.current_screen_hash() == step["expect_screen_hash"]
        next_hash = driver.apply(step["aid"], step.get("inputs", {{}}))
        assert next_hash == step["expect_next_screen_hash"]

    response = driver.extract_response()
    for name, expected_value in case["expected_response"].items():
        if expected_value != REDACTED:
            assert response[name] == expected_value
    driver.assert_no_unexpected_transition()
'''
