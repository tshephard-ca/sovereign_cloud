from __future__ import annotations

import re
from typing import Any

PATH_TOKEN_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[([0-9]+)\]")


def extract_json_path(payload: Any, path: str | None) -> tuple[Any, list[str]]:
    if not path:
        return None, ["RESPONSE_EXTRACTOR_MISSING_FIELD"]
    if not path.startswith("$"):
        return None, ["RESPONSE_EXTRACTOR_MISSING_FIELD"]
    current = payload
    try:
        for key, index in PATH_TOKEN_RE.findall(path[1:]):
            if key:
                if not isinstance(current, dict) or key not in current:
                    return None, ["RESPONSE_EXTRACTOR_MISSING_FIELD"]
                current = current[key]
            else:
                if not isinstance(current, list):
                    return None, ["RESPONSE_EXTRACTOR_MISSING_FIELD"]
                idx = int(index)
                if idx >= len(current):
                    return None, ["RESPONSE_EXTRACTOR_MISSING_FIELD"]
                current = current[idx]
    except (TypeError, ValueError):
        return None, ["RESPONSE_EXTRACTOR_MISSING_FIELD"]
    return current, []
