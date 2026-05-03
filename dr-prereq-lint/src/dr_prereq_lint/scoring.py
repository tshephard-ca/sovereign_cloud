"""Shared severity and confidence ordering."""

from __future__ import annotations


CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "REVIEW": 2, "INFO": 3}


def max_confidence(values: list[str]) -> str:
    if not values:
        return "LOW"
    return max(values, key=lambda value: CONFIDENCE_ORDER.get(value, 0))


def sort_severity(value: str) -> int:
    return SEVERITY_ORDER.get(value, 99)
