from __future__ import annotations

from inference_placement_bench.token_estimate import output_tokens_from_text


def test_token_usage_returned_from_response_is_marked_exact():
    tokens, source = output_tokens_from_text(12, "ignored")
    assert tokens == 12
    assert source == "EXACT_FROM_RESPONSE"


def test_token_usage_absent_falls_back_to_heuristic_estimate():
    tokens, source = output_tokens_from_text(None, "abcd efgh")
    assert tokens >= 2
    assert source == "HEURISTIC_ESTIMATE"
