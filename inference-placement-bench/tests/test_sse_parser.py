from __future__ import annotations

from inference_placement_bench.sse_parser import parse_sse_lines


def test_sse_parser_handles_data_lines_and_done_marker():
    result = parse_sse_lines(['data: {"a": 1}', "data: [DONE]"])
    assert result.done_observed is True
    assert result.payloads == [{"a": 1}]


def test_sse_parser_warns_when_finish_not_observed():
    result = parse_sse_lines(['data: {"a": 1}'])
    assert "STREAM_FINISH_NOT_OBSERVED" in result.warnings
