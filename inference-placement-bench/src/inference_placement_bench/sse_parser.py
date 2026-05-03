from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class SSEParseResult:
    payloads: list[dict] = field(default_factory=list)
    done_observed: bool = False
    event_count: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_sse_lines(lines: Iterable[str]) -> SSEParseResult:
    result = SSEParseResult()
    for line in lines:
        stripped = line.strip()
        if not stripped or not stripped.startswith("data:"):
            continue
        result.event_count += 1
        data = stripped[len("data:") :].strip()
        if data == "[DONE]":
            result.done_observed = True
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            result.warnings.append("RESPONSE_PARSE_FAILED")
            continue
        result.payloads.append(payload)
    if not result.done_observed:
        result.warnings.append("STREAM_FINISH_NOT_OBSERVED")
    return result
