from __future__ import annotations

from math import ceil

from .models import PromptRecord


def estimate_tokens(text: str | None, chars_per_token: int = 4) -> int:
    if not text:
        return 0
    return max(1, ceil(len(text) / chars_per_token))


def input_tokens_from_prompt(prompt: PromptRecord, chars_per_token: int = 4) -> tuple[int, str]:
    if prompt.input_tokens_estimate is not None:
        return prompt.input_tokens_estimate, "USER_ESTIMATE"
    return estimate_tokens(prompt.prompt, chars_per_token), "HEURISTIC_ESTIMATE"


def output_tokens_from_text(
    response_usage_tokens: int | None,
    text: str | None,
    expected_estimate: int | None = None,
    chars_per_token: int = 4,
) -> tuple[int, str]:
    if response_usage_tokens is not None:
        return response_usage_tokens, "EXACT_FROM_RESPONSE"
    if expected_estimate is not None:
        return expected_estimate, "USER_ESTIMATE"
    return estimate_tokens(text, chars_per_token), "HEURISTIC_ESTIMATE"
