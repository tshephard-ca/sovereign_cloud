from __future__ import annotations

import pytest

from inference_placement_bench.payload_template import render_template


def test_payload_template_preserves_boolean_and_integer_types():
    rendered = render_template(
        {"stream": "{{streaming}}", "max_tokens": "{{max_output_tokens}}", "prompt": "{{prompt}}"},
        {"streaming": True, "max_output_tokens": 123, "prompt": "hello"},
    )
    assert rendered["stream"] is True
    assert rendered["max_tokens"] == 123
    assert rendered["prompt"] == "hello"


def test_payload_template_fails_unknown_placeholder():
    with pytest.raises(ValueError):
        render_template({"bad": "{{unknown}}"}, {})
