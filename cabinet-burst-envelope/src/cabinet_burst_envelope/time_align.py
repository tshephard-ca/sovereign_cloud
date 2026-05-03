from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from .models import AlignmentResult, CoverageStats, PowerReading, TemperatureReading, TimeBucket
from .normalize import add_unique, isoformat_z, parse_timestamp, round_float


def _bucket_index(timestamp: datetime, start: datetime, bucket_minutes: int) -> int:
    delta = timestamp - start
    return int(delta.total_seconds() // (bucket_minutes * 60))


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _feed_key(feed_id: str | None) -> str:
    if not feed_id:
        return "UNKNOWN"
    raw = feed_id.strip()
    upper = raw.upper()
    return upper if upper in {"A", "B"} else raw


def _height_for(reading: TemperatureReading) -> str:
    if reading.height in {"top", "middle", "bottom"}:
        return reading.height
    if reading.position == "front_top":
        return "top"
    if reading.position == "front_middle":
        return "middle"
    if reading.position == "front_bottom":
        return "bottom"
    return "unknown"


def is_valid_inlet_sensor(reading: TemperatureReading) -> bool:
    if reading.sensor_role == "inlet":
        return True
    return reading.position.startswith("front_")


def _longest_missing_gap_minutes(flags: list[bool], bucket_minutes: int) -> int:
    longest = 0
    current = 0
    for present in flags:
        if present:
            longest = max(longest, current)
            current = 0
        else:
            current += 1
    longest = max(longest, current)
    return longest * bucket_minutes


def align_timeseries(
    power_rows: list[PowerReading],
    temperature_rows: list[TemperatureReading],
    cabinet_id: str,
    config: dict,
    window_days: int = 7,
    bucket_minutes: int = 5,
    now: str | datetime | None = None,
) -> AlignmentResult:
    reason_codes: list[str] = []
    warnings: list[str] = []
    missing_data: list[str] = []

    if now is not None:
        window_end = parse_timestamp(now)[0] if isinstance(now, str) else now
        if window_end.tzinfo is None:
            window_end = window_end.replace(tzinfo=UTC)
        else:
            window_end = window_end.astimezone(UTC)
    else:
        timestamps = [row.timestamp for row in power_rows] + [row.timestamp for row in temperature_rows]
        window_end = max(timestamps) if timestamps else datetime.now(tz=UTC)
    window_start = window_end - timedelta(days=window_days)
    expected_buckets = int((window_days * 24 * 60) // bucket_minutes)

    buckets = [
        TimeBucket(
            timestamp=window_start + timedelta(minutes=index * bucket_minutes),
            cabinet_id=cabinet_id,
        )
        for index in range(expected_buckets)
    ]

    power_by_bucket: dict[int, list[PowerReading]] = defaultdict(list)
    for row in power_rows:
        if row.cabinet_id != cabinet_id:
            continue
        if window_start <= row.timestamp < window_end:
            index = _bucket_index(row.timestamp, window_start, bucket_minutes)
            if 0 <= index < expected_buckets:
                power_by_bucket[index].append(row)

    temp_by_bucket: dict[int, list[TemperatureReading]] = defaultdict(list)
    valid_inlet_seen = False
    ambient_or_unknown_count = 0
    for row in temperature_rows:
        if row.cabinet_id != cabinet_id:
            continue
        if is_valid_inlet_sensor(row):
            valid_inlet_seen = True
        elif row.sensor_role in {"ambient", "unknown"} or row.position in {"ambient", "unknown"}:
            ambient_or_unknown_count += 1
        if window_start <= row.timestamp < window_end:
            index = _bucket_index(row.timestamp, window_start, bucket_minutes)
            if 0 <= index < expected_buckets:
                temp_by_bucket[index].append(row)

    if not valid_inlet_seen:
        add_unique(reason_codes, "NO_VALID_INLET_SENSOR")
        add_unique(missing_data, "NO_VALID_INLET_SENSOR")
        if ambient_or_unknown_count and not temperature_rows:
            add_unique(reason_codes, "AMBIENT_SENSOR_ONLY")
        elif ambient_or_unknown_count:
            add_unique(reason_codes, "AMBIENT_SENSOR_ONLY")

    for index, bucket in enumerate(buckets):
        p_rows = power_by_bucket.get(index, [])
        if p_rows:
            if any(row.reading_quality in {"estimated", "stale"} for row in p_rows):
                bucket.power_bucket_quality = "review"
            else:
                bucket.power_bucket_quality = "good"
            if any(row.reading_scope == "unknown" for row in p_rows):
                add_unique(reason_codes, "READING_SCOPE_UNKNOWN")
                add_unique(warnings, "READING_SCOPE_UNKNOWN")
                bucket.notes.append("READING_SCOPE_UNKNOWN")

            total_values = [row.reading_kw for row in p_rows if row.reading_scope == "total_cabinet"]
            feed_values: dict[str, list[float]] = defaultdict(list)
            outlet_values: dict[str, list[float]] = defaultdict(list)
            unknown_values = [row.reading_kw for row in p_rows if row.reading_scope == "unknown"]
            for row in p_rows:
                if row.reading_scope == "feed_total":
                    feed_values[_feed_key(row.feed_id)].append(row.reading_kw)
                elif row.reading_scope == "outlet":
                    outlet_values[row.outlet_id or row.source_row_id or "unknown"].append(row.reading_kw)

            feed_power = {
                feed_id: float(_average(values) or 0.0)
                for feed_id, values in sorted(feed_values.items())
            }
            if feed_power:
                bucket.feed_power_kw = {key: round_float(value, 3) for key, value in feed_power.items()}

            if total_values:
                bucket.cabinet_power_kw = round_float(float(_average(total_values) or 0.0), 3)
            elif feed_power:
                bucket.cabinet_power_kw = round_float(sum(feed_power.values()), 3)
            elif outlet_values:
                bucket.cabinet_power_kw = round_float(sum(float(_average(values) or 0.0) for values in outlet_values.values()), 3)
            elif unknown_values:
                bucket.cabinet_power_kw = round_float(float(_average(unknown_values) or 0.0), 3)
            else:
                bucket.power_bucket_quality = "missing"

        t_rows = temp_by_bucket.get(index, [])
        valid_sensor_values: dict[str, list[float]] = defaultdict(list)
        sensor_heights: dict[str, str] = {}
        for row in t_rows:
            if is_valid_inlet_sensor(row):
                valid_sensor_values[row.sensor_id].append(row.inlet_temp_c)
                sensor_heights[row.sensor_id] = _height_for(row)

        if valid_sensor_values:
            sensor_avgs = {
                sensor_id: float(_average(values) or 0.0)
                for sensor_id, values in valid_sensor_values.items()
            }
            bucket.max_inlet_temp_c = round_float(max(sensor_avgs.values()), 3)
            top = [value for sensor_id, value in sensor_avgs.items() if sensor_heights.get(sensor_id) == "top"]
            middle = [value for sensor_id, value in sensor_avgs.items() if sensor_heights.get(sensor_id) == "middle"]
            bottom = [value for sensor_id, value in sensor_avgs.items() if sensor_heights.get(sensor_id) == "bottom"]
            bucket.top_inlet_temp_c = round_float(max(top), 3) if top else None
            bucket.middle_inlet_temp_c = round_float(max(middle), 3) if middle else None
            bucket.bottom_inlet_temp_c = round_float(max(bottom), 3) if bottom else None
            bucket.temperature_bucket_quality = "review" if any(row.reading_quality in {"estimated", "stale"} for row in t_rows) else "good"

        has_power = bucket.cabinet_power_kw is not None
        has_temp = bucket.max_inlet_temp_c is not None
        if has_power and has_temp:
            bucket.aligned_bucket_quality = "good" if bucket.power_bucket_quality == "good" and bucket.temperature_bucket_quality == "good" else "review"
        elif has_power or has_temp:
            bucket.aligned_bucket_quality = "partial"
        else:
            bucket.aligned_bucket_quality = "missing"
        if not has_power:
            bucket.notes.append("POWER_MISSING")
        if not has_temp:
            bucket.notes.append("TEMPERATURE_MISSING")

    power_present = [bucket.cabinet_power_kw is not None for bucket in buckets]
    temperature_present = [bucket.max_inlet_temp_c is not None for bucket in buckets]
    aligned_present = [power and temp for power, temp in zip(power_present, temperature_present)]
    coverage = CoverageStats(
        expected_buckets=expected_buckets,
        power_buckets=sum(power_present),
        temperature_buckets=sum(temperature_present),
        aligned_buckets=sum(aligned_present),
        power_coverage_pct=round_float(sum(power_present) / expected_buckets * 100, 3) if expected_buckets else 0.0,
        temperature_coverage_pct=round_float(sum(temperature_present) / expected_buckets * 100, 3) if expected_buckets else 0.0,
        aligned_coverage_pct=round_float(sum(aligned_present) / expected_buckets * 100, 3) if expected_buckets else 0.0,
        longest_power_gap_minutes=_longest_missing_gap_minutes(power_present, bucket_minutes),
        longest_temperature_gap_minutes=_longest_missing_gap_minutes(temperature_present, bucket_minutes),
    )

    minimum_coverage = float(config["minimum_coverage_pct"])
    if coverage.power_coverage_pct < minimum_coverage:
        add_unique(reason_codes, "POWER_COVERAGE_LOW")
        add_unique(warnings, "POWER_COVERAGE_LOW")
    if coverage.temperature_coverage_pct < minimum_coverage:
        add_unique(reason_codes, "TEMPERATURE_COVERAGE_LOW")
        add_unique(warnings, "TEMPERATURE_COVERAGE_LOW")
    if coverage.aligned_coverage_pct < minimum_coverage:
        add_unique(reason_codes, "ALIGNED_COVERAGE_LOW")
        add_unique(warnings, "ALIGNED_COVERAGE_LOW")
    if coverage.longest_power_gap_minutes > int(config["long_gap_minutes"]):
        add_unique(reason_codes, "LONG_POWER_GAP")
        add_unique(warnings, "LONG_POWER_GAP")
    if coverage.longest_temperature_gap_minutes > int(config["long_gap_minutes"]):
        add_unique(reason_codes, "LONG_TEMPERATURE_GAP")
        add_unique(warnings, "LONG_TEMPERATURE_GAP")

    for bucket in buckets:
        bucket.timestamp = parse_timestamp(isoformat_z(bucket.timestamp))[0]

    return AlignmentResult(
        cabinet_id=cabinet_id,
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
        bucket_minutes=bucket_minutes,
        buckets=buckets,
        coverage=coverage,
        reason_codes=reason_codes,
        warnings=warnings,
        missing_data=missing_data,
    )
