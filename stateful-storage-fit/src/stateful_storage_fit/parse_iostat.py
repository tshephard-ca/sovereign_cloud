from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

from .models import IoDeviceSample


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def _canonical_field(name: str) -> str:
    return name.strip().rstrip(":").lower()


def _await_value(metrics: dict[str, float]) -> Optional[float]:
    values = [
        metrics.get("await"),
        metrics.get("r_await"),
        metrics.get("w_await"),
    ]
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _queue_value(metrics: dict[str, float]) -> Optional[float]:
    return metrics.get("aqu-sz", metrics.get("avgqu-sz"))


def _is_ignored_device(device: str) -> bool:
    return device.startswith(("loop", "ram", "fd"))


def parse_iostat_text(text: str) -> tuple[dict[str, IoDeviceSample], list[str], dict[str, Optional[float] | int]]:
    warnings: list[str] = []
    reports: list[list[tuple[str, dict[str, float]]]] = []
    current_header: list[str] | None = None
    current_report: list[tuple[str, dict[str, float]]] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        first = parts[0].rstrip(":").lower()
        if first == "device":
            if current_header is not None and current_report:
                reports.append(current_report)
                current_report = []
            current_header = [_canonical_field(part) for part in parts]
            current_header[0] = "device"
            continue
        if current_header is None:
            continue
        if len(parts) < 2:
            continue
        device = parts[0]
        metrics: dict[str, float] = {}
        for field, value_s in zip(current_header[1:], parts[1:]):
            value = _to_float(value_s)
            if value is not None:
                metrics[field] = value
        if metrics:
            current_report.append((device, metrics))

    if current_header is not None and current_report:
        reports.append(current_report)

    if not reports:
        return {}, ["IOSTAT_PARSE_FAILED"], {
            "max_observed_await_ms": None,
            "max_observed_util_pct": None,
            "reports_seen": 0,
        }

    used_reports = reports[1:] if len(reports) > 1 else reports
    accum: dict[str, defaultdict[str, float]] = {}
    counts: dict[str, int] = defaultdict(int)
    max_await_by_device: dict[str, float] = {}
    max_util_by_device: dict[str, float] = {}
    global_max_await: Optional[float] = None
    global_max_util: Optional[float] = None

    for report in used_reports:
        for device, metrics in report:
            if device not in accum:
                accum[device] = defaultdict(float)
            counts[device] += 1
            for key, value in metrics.items():
                accum[device][key] += value
            await_value = _await_value(metrics)
            util_value = metrics.get("%util")
            if await_value is not None:
                max_await_by_device[device] = max(max_await_by_device.get(device, await_value), await_value)
                global_max_await = await_value if global_max_await is None else max(global_max_await, await_value)
            if util_value is not None:
                max_util_by_device[device] = max(max_util_by_device.get(device, util_value), util_value)
                global_max_util = util_value if global_max_util is None else max(global_max_util, util_value)

    samples: dict[str, IoDeviceSample] = {}
    for device, sums in accum.items():
        count = counts[device]
        averaged = {key: value / count for key, value in sums.items()}
        await_value = _await_value(averaged)
        samples[device] = IoDeviceSample(
            device=device,
            await_ms=await_value,
            r_await_ms=averaged.get("r_await"),
            w_await_ms=averaged.get("w_await"),
            util_pct=averaged.get("%util"),
            queue_depth=_queue_value(averaged),
            samples_count=count,
            max_await_ms=max_await_by_device.get(device),
            max_util_pct=max_util_by_device.get(device),
            raw_metrics=dict(averaged),
        )

    non_ignored = [sample for sample in samples.values() if not _is_ignored_device(sample.device)]
    if not non_ignored:
        warnings.append("IOSTAT_NO_NON_SYSTEM_DEVICES")
    return samples, warnings, {
        "max_observed_await_ms": global_max_await,
        "max_observed_util_pct": global_max_util,
        "reports_seen": len(reports),
    }


def parse_iostat_file(path: Path) -> tuple[dict[str, IoDeviceSample], list[str], dict[str, Optional[float] | int]]:
    return parse_iostat_text(path.read_text(encoding="utf-8", errors="replace"))

