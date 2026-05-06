from __future__ import annotations

import pytest

from host_screen_contracts.replay_driver import ReplayMismatch, TraceReplayDriver
from host_screen_contracts.trace_schema import ActionEvent


def test_replay_driver_validates_happy_path_trace(order_events, order_result):
    result = order_result()
    driver = TraceReplayDriver(order_events, result.contract)
    case = result.replay_case
    assert driver.current_screen_hash() == case.start_screen_hash
    for step in case.steps:
        assert driver.apply(step.aid, step.inputs) == step.expect_next_screen_hash
    assert driver.extract_response() == case.expected_response
    driver.assert_no_unexpected_transition()


def test_replay_driver_recomputes_hashes_from_trace(order_events, order_result):
    result = order_result()
    result.contract.screens[0].screen_hash = "not_the_current_hash"
    driver = TraceReplayDriver(order_events, result.contract)
    assert driver.current_screen_hash() == result.replay_case.start_screen_hash


def test_replay_driver_reports_mismatch_conditions(order_events, order_result):
    result = order_result()

    driver = TraceReplayDriver(order_events, result.contract)
    with pytest.raises(ReplayMismatch, match="unapplied actions"):
        driver.assert_no_unexpected_transition()

    driver = TraceReplayDriver(order_events, result.contract)
    with pytest.raises(ReplayMismatch, match="expected aid"):
        driver.apply("F3", {"order_number": "10004567"})

    driver = TraceReplayDriver(order_events, result.contract)
    with pytest.raises(ReplayMismatch, match="unexpected input field"):
        driver.apply("ENTER", {"not_in_contract": "10004567"})

    driver = TraceReplayDriver(order_events, result.contract)
    with pytest.raises(ReplayMismatch, match="input value mismatch"):
        driver.apply("ENTER", {"order_number": "BAD"})

    changed_contract = result.contract.model_copy(deep=True)
    changed_contract.request_fields[0].field_id = "missing"
    changed_contract.request_fields[0].row = 9
    changed_contract.request_fields[0].col = 9
    driver = TraceReplayDriver(order_events, changed_contract)
    with pytest.raises(ReplayMismatch, match="was not recorded"):
        driver.apply("ENTER", {"order_number": "10004567"})

    driver = TraceReplayDriver(order_events, result.contract)
    driver.apply("ENTER", {"order_number": "10004567"})
    with pytest.raises(ReplayMismatch, match="no recorded action remains"):
        driver.apply("ENTER", {"order_number": "10004567"})

    no_screen_driver = TraceReplayDriver([ActionEvent(type="action", seq=1, aid="ENTER")], result.contract)
    with pytest.raises(ReplayMismatch, match="trace has no screens"):
        _ = no_screen_driver.current_screen

    no_next_screen_events = [
        order_events[0],
        ActionEvent(type="action", seq=2, aid="ENTER", inputs=[{"field_id": "f_04_32", "row": 4, "col": 32, "value": "10004567"}]),
    ]
    driver = TraceReplayDriver(no_next_screen_events, result.contract)
    with pytest.raises(ReplayMismatch, match="no following screen"):
        driver.apply("ENTER", {"order_number": "10004567"})

    missing_response_contract = result.contract.model_copy(deep=True)
    missing_response_contract.response_fields[0].screen_ref = "screen_999"
    driver = TraceReplayDriver(order_events, missing_response_contract)
    assert driver.extract_response()[missing_response_contract.response_fields[0].name] == ""
