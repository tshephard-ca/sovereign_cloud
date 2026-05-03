from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import NvidiaSmiGpuInfo, NvidiaSmiQueryResult


def parse_nvidia_smi_query(path: Path) -> NvidiaSmiQueryResult:
    result = NvidiaSmiQueryResult(present=path.exists(), reason_codes=["NVIDIA_SMI_QUERY_PRESENT"] if path.exists() else ["NVIDIA_SMI_QUERY_MISSING"])
    if not path.exists():
        return result
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    except ET.ParseError as exc:
        result.errors.append(str(exc))
        result.reason_codes.append("NVIDIA_SMI_QUERY_PARSE_FAILED")
        return result
    result.parsed = True
    result.driver_version = _first_text(root, {"driver_version"})
    result.cuda_version = _first_text(root, {"cuda_version"})
    for gpu in _children_named(root, "gpu"):
        info = NvidiaSmiGpuInfo(
            uuid=_first_text(gpu, {"uuid", "gpu_uuid"}),
            product_name=_first_text(gpu, {"product_name", "name"}),
            vbios_version=_first_text(gpu, {"vbios_version"}),
            ecc_mode=_extract_ecc_mode(gpu),
            retired_pages=_extract_retired_pages(gpu),
            temperature_celsius=_parse_float(_first_text(gpu, {"gpu_temp", "temperature", "temp"})),
            power_draw_watts=_parse_float(_first_text(gpu, {"power_draw", "power"})),
            clocks_throttle_reasons=_extract_throttle_reasons(gpu),
            mig_mode=_extract_mig_mode(gpu),
            serial=_first_text(gpu, {"serial", "serial_number"}),
        )
        result.gpus.append(info)
    return result


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children_named(root: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local(element.tag) == name]


def _first_text(root: ET.Element, names: set[str]) -> str | None:
    for element in root.iter():
        if _local(element.tag) in names and element.text:
            text = element.text.strip()
            if text and text.upper() != "N/A":
                return text
    return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def _extract_ecc_mode(gpu: ET.Element) -> str | None:
    for key in ("current_ecc", "ecc_mode", "current"):
        text = _first_text(gpu, {key})
        if text and text.lower() in {"enabled", "disabled"}:
            return text.lower()
    return None


def _extract_mig_mode(gpu: ET.Element) -> str | None:
    for key in ("current_mig", "mig_mode", "current"):
        text = _first_text(gpu, {key})
        if text and text.lower() in {"enabled", "disabled"}:
            return text.lower()
    return None


def _extract_retired_pages(gpu: ET.Element) -> int:
    total = 0
    for element in gpu.iter():
        name = _local(element.tag)
        if "retired" in name and element.text:
            value = _parse_float(element.text)
            if value is not None:
                total += int(value)
    return total


def _extract_throttle_reasons(gpu: ET.Element) -> list[str]:
    reasons: list[str] = []
    for element in gpu.iter():
        name = _local(element.tag)
        if "clocks_throttle" in name or "clocks_event" in name or "throttle_reason" in name:
            continue
        if element.text and element.text.strip().lower() in {"active", "yes", "true"}:
            reasons.append(name.upper())
    return sorted(set(reasons))
