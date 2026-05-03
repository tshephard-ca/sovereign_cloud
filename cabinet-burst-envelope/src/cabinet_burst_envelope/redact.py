from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any


PREFIX_BY_KIND = {
    "cabinet": "cabinet",
    "display_name": "cabinet",
    "pdu": "pdu",
    "sensor": "sensor",
    "circuit": "circuit",
    "source": "source",
}


class Redactor:
    def __init__(self) -> None:
        self._maps: dict[str, dict[str, str]] = defaultdict(dict)

    def redact(self, kind: str, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        prefix = PREFIX_BY_KIND.get(kind, kind)
        mapping = self._maps[kind]
        if value not in mapping:
            mapping[value] = f"{prefix}_{len(mapping) + 1:03d}"
        return mapping[value]

    def redact_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = deepcopy(payload)
        for key, kind in {
            "cabinet_id": "cabinet",
            "display_name": "display_name",
            "pdu_id": "pdu",
            "sensor_id": "sensor",
            "circuit_id": "circuit",
            "source": "source",
        }.items():
            if key in redacted:
                redacted[key] = self.redact(kind, redacted[key])
        return redacted
