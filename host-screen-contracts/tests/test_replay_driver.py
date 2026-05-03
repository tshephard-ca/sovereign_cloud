from __future__ import annotations

from host_screen_contracts.replay_driver import TraceReplayDriver


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
