from __future__ import annotations

import re
from typing import Any

from .field_map import FieldMapEntry


REDACTED = "<REDACTED>"
SENSITIVE_NAME_RE = re.compile(r"(password|pass|secret|token|ssn|sin|account|card|dob)", re.IGNORECASE)


def is_sensitive_name(name: str | None) -> bool:
    return bool(name and SENSITIVE_NAME_RE.search(name))


def should_redact(name: str | None, field_map_entry: FieldMapEntry | None, *, redact: bool) -> bool:
    if not redact:
        return False
    if field_map_entry and field_map_entry.sensitive is False:
        return False
    if field_map_entry and field_map_entry.sensitive is True:
        return True
    return is_sensitive_name(name)


def redact_value(value: Any, name: str | None = None, field_map_entry: FieldMapEntry | None = None, *, redact: bool) -> Any:
    if should_redact(name, field_map_entry, redact=redact):
        return REDACTED
    return value
