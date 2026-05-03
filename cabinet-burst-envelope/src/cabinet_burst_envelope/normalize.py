from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_FLOOR
from typing import Iterable


def stable_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def add_unique(target: list[str], *values: str) -> None:
    for value in values:
        if value and value not in target:
            target.append(value)


def parse_timestamp(value: str) -> tuple[datetime, bool]:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("timestamp is required")
    normalized = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    timezone_unknown = dt.tzinfo is None
    if timezone_unknown:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt, timezone_unknown


def isoformat_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_optional_float(value: object) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw == "":
        return None
    return float(raw)


def parse_required_float(value: object, field_name: str) -> float:
    parsed = parse_optional_float(value)
    if parsed is None:
        raise ValueError(f"{field_name} is required")
    return parsed


def lower_or_default(value: object, default: str) -> str:
    raw = "" if value is None else str(value).strip()
    return raw.lower() if raw else default


def text_or_none(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    return raw or None


def round_float(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def floor_one_decimal(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0:
        return 0.0
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_FLOOR))


def safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
