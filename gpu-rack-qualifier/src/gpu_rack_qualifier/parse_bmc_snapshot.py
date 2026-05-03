from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BmcSensor, BmcSnapshot


def parse_bmc_snapshot(path: Path) -> BmcSnapshot:
    result = BmcSnapshot(present=path.exists(), reason_codes=["BMC_SNAPSHOT_PRESENT"] if path.exists() else ["BMC_SNAPSHOT_MISSING"])
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        result.errors.append(str(exc))
        result.reason_codes.append("BMC_SENSOR_PARSE_FAILED")
        return result
    try:
        result.sensors = [_normalize_sensor(item) for item in _iter_sensor_dicts(data)]
        result.parsed = True
        _summarize_snapshot(result)
    except Exception as exc:  # pragma: no cover - defensive parser boundary
        result.errors.append(str(exc))
        result.reason_codes.append("BMC_SENSOR_PARSE_FAILED")
    return result


def _iter_sensor_dicts(data: Any) -> list[dict[str, Any]]:
    sensors: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key in ("sensors", "Sensors", "Members", "Temperatures", "Fans", "PowerSupplies", "Voltages"):
            value = data.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        enriched = dict(item)
                        if key in {"Temperatures"}:
                            enriched.setdefault("SensorType", "Temperature")
                        if key in {"Fans"}:
                            enriched.setdefault("SensorType", "Fan")
                        if key in {"PowerSupplies"}:
                            enriched.setdefault("SensorType", "Power")
                        if key in {"Voltages"}:
                            enriched.setdefault("SensorType", "Voltage")
                        sensors.append(enriched)
        for value in data.values():
            if isinstance(value, dict):
                sensors.extend(_iter_sensor_dicts(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        sensors.extend(_iter_sensor_dicts(item))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                sensors.append(item)
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for item in sensors:
        marker = id(item)
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


def _normalize_sensor(item: dict[str, Any]) -> BmcSensor:
    status = item.get("Status") if isinstance(item.get("Status"), dict) else {}
    name = item.get("sensor_name") or item.get("Name") or item.get("MemberId") or item.get("Id") or "unknown"
    sensor_type = _sensor_type(str(item.get("sensor_type") or item.get("SensorType") or item.get("@odata.type") or name))
    return BmcSensor(
        sensor_name=str(name),
        sensor_type=sensor_type,
        reading=_number(item.get("reading") or item.get("Reading") or item.get("ReadingCelsius") or item.get("ReadingVolts") or item.get("ReadingWatts")),
        units=item.get("units") or item.get("ReadingUnits") or _default_units(sensor_type),
        status_state=_normalize_state(item.get("status_state") or status.get("State") or item.get("State")),
        status_health=_normalize_health(item.get("status_health") or status.get("Health") or item.get("Health")),
        upper_warning=_number(item.get("upper_warning") or item.get("UpperThresholdNonCritical")),
        upper_critical=_number(item.get("upper_critical") or item.get("UpperThresholdCritical")),
        lower_warning=_number(item.get("lower_warning") or item.get("LowerThresholdNonCritical")),
        lower_critical=_number(item.get("lower_critical") or item.get("LowerThresholdCritical")),
        serial=item.get("serial") or item.get("SerialNumber"),
    )


def _summarize_snapshot(result: BmcSnapshot) -> None:
    for sensor in result.sensors:
        health = (sensor.status_health or "").lower()
        state = (sensor.status_state or "").lower()
        if health == "warning":
            result.warning_count += 1
        if health == "critical":
            result.critical_count += 1
        if sensor.sensor_type == "fan" and (health in {"warning", "critical"} or sensor.reading == 0):
            result.fan_failure_count += 1
        if sensor.sensor_type == "temperature" and sensor.reading is not None:
            result.temp_max_celsius = sensor.reading if result.temp_max_celsius is None else max(result.temp_max_celsius, sensor.reading)
        if sensor.sensor_type == "power" and (health == "warning" or "redund" in sensor.sensor_name.lower() and health != "ok"):
            result.power_warning_count += 1
        if sensor.sensor_type in {"power", "voltage"} and health == "critical":
            result.power_critical_count += 1
        if state == "absent" and sensor.sensor_type == "fan" and health in {"warning", "critical"}:
            result.fan_failure_count += 1
    if result.critical_count:
        result.reason_codes.append("BMC_HEALTH_CRITICAL")
    elif result.warning_count:
        result.reason_codes.append("BMC_HEALTH_WARNING")
    else:
        result.reason_codes.append("BMC_HEALTH_OK")
    if result.fan_failure_count:
        result.reason_codes.append("BMC_FAN_FAILURE")


def _sensor_type(raw: str) -> str:
    lower = raw.lower()
    if "temp" in lower or "thermal" in lower:
        return "temperature"
    if "fan" in lower:
        return "fan"
    if "power" in lower or "psu" in lower:
        return "power"
    if "volt" in lower:
        return "voltage"
    if "current" in lower:
        return "current"
    if "energy" in lower:
        return "energy"
    return "unknown"


def _default_units(sensor_type: str) -> str | None:
    return {"temperature": "C", "fan": "RPM", "power": "W", "voltage": "V"}.get(sensor_type)


def _normalize_health(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"ok", "enabled"}:
        return "OK"
    if text in {"warning", "warn", "degraded"}:
        return "Warning"
    if text in {"critical", "fail", "failed"}:
        return "Critical"
    if text in {"absent", "unknown"}:
        return text.title()
    return str(value).strip()


def _normalize_state(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip().title()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
