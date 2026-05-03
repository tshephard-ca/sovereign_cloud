from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

ALLOWED_PLACEHOLDERS = {
    "model_name",
    "prompt",
    "max_output_tokens",
    "streaming",
    "temperature",
}
PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def render_template(template: Any, values: dict[str, Any]) -> Any:
    unknown = find_unknown_placeholders(template)
    if unknown:
        raise ValueError(f"unknown placeholders: {', '.join(sorted(unknown))}")
    return _render(deepcopy(template), values)


def find_unknown_placeholders(template: Any) -> set[str]:
    found = set()
    for placeholder in _walk_placeholders(template):
        if placeholder not in ALLOWED_PLACEHOLDERS:
            found.add(placeholder)
    return found


def _walk_placeholders(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_walk_placeholders(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_walk_placeholders(item))
        return result
    if isinstance(value, str):
        return PLACEHOLDER_RE.findall(value)
    return []


def _render(value: Any, values: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, values) for item in value]
    if isinstance(value, str):
        match = PLACEHOLDER_RE.fullmatch(value)
        if match:
            key = match.group(1)
            return values.get(key)

        def replace(match_obj: re.Match[str]) -> str:
            key = match_obj.group(1)
            replacement = values.get(key)
            return "" if replacement is None else str(replacement)

        return PLACEHOLDER_RE.sub(replace, value)
    return value
