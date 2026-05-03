from __future__ import annotations

import math
import re
from typing import Optional

from .models import IoDeviceSample


GIB = 1024**3


def bytes_to_gib(value: int | None) -> Optional[float]:
    if value is None:
        return None
    return value / GIB


def storage_request_gib(used_gib: float | None, config: dict) -> Optional[int]:
    if used_gib is None:
        return None
    with_headroom = used_gib * (1 + float(config["storage_headroom_pct"]) / 100)
    with_min_extra = used_gib + float(config["storage_min_extra_gib"])
    return int(math.ceil(max(with_headroom, with_min_extra)))


def capacity_risk(capacity_pct: float | None, config: dict) -> str:
    if capacity_pct is None:
        return "UNKNOWN"
    if capacity_pct >= float(config["critical_capacity_used_pct"]):
        return "HIGH"
    if capacity_pct >= float(config["high_capacity_used_pct"]):
        return "MEDIUM"
    return "LOW"


def latency_risk_from_values(
    await_ms: float | None,
    util_pct: float | None,
    queue_depth: float | None,
    config: dict,
) -> str:
    if await_ms is None and util_pct is None and queue_depth is None:
        return "UNKNOWN"
    if await_ms is not None and await_ms >= float(config["latency_high_await_ms"]):
        return "HIGH"
    if util_pct is not None and util_pct >= float(config["util_high_pct"]):
        return "HIGH"
    if queue_depth is not None and queue_depth >= float(config["queue_high_depth"]):
        return "HIGH"
    if await_ms is not None and await_ms >= float(config["latency_medium_await_ms"]):
        return "MEDIUM"
    if util_pct is not None and util_pct >= float(config["util_medium_pct"]):
        return "MEDIUM"
    if queue_depth is not None and queue_depth >= float(config["queue_medium_depth"]):
        return "MEDIUM"
    return "LOW"


def latency_risk_for_sample(sample: IoDeviceSample | None, config: dict) -> str:
    if sample is None:
        return "UNKNOWN"
    await_value = sample.max_await_ms if sample.max_await_ms is not None else sample.await_ms
    util_value = sample.max_util_pct if sample.max_util_pct is not None else sample.util_pct
    return latency_risk_from_values(await_value, util_value, sample.queue_depth, config)


def worst_risk(risks: list[str]) -> str:
    order = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    if not risks:
        return "UNKNOWN"
    return max(risks, key=lambda risk: order.get(risk, 0))


def parent_iostat_device(source: str) -> tuple[str | None, bool]:
    if not source.startswith("/dev/"):
        return None, False
    name = source.rsplit("/", 1)[-1]
    if name.startswith("mapper/") or "/mapper/" in source:
        return None, True
    if name.startswith("dm-"):
        return name, False
    nvme = re.match(r"^(nvme\d+n\d+)p\d+$", name)
    if nvme:
        return nvme.group(1), False
    mmc = re.match(r"^(mmcblk\d+)p\d+$", name)
    if mmc:
        return mmc.group(1), False
    sd = re.match(r"^([a-z]+)\d+$", name)
    if sd:
        return sd.group(1), False
    return name, False

