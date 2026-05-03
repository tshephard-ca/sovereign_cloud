from __future__ import annotations

from .models import PowerStats, TemperatureStats, TimeBucket
from .normalize import add_unique, round_float


def percentile(values: list[float], pct: float) -> float | None:
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    rank = (pct / 100.0) * (len(clean) - 1)
    low = int(rank)
    high = min(low + 1, len(clean) - 1)
    fraction = rank - low
    return clean[low] + (clean[high] - clean[low]) * fraction


def rolling_averages(values: list[float | None], window_size: int) -> list[float]:
    if window_size <= 1:
        return [float(value) for value in values if value is not None]
    out: list[float] = []
    for index in range(window_size - 1, len(values)):
        window = values[index - window_size + 1 : index + 1]
        if all(value is not None for value in window):
            out.append(sum(float(value) for value in window) / window_size)
    return out


def max_ramp_per_min(values: list[float | None], bucket_minutes: int) -> float | None:
    max_ramp: float | None = None
    previous: float | None = None
    for value in values:
        if value is None:
            previous = None
            continue
        if previous is not None:
            ramp = abs(value - previous) / bucket_minutes
            max_ramp = ramp if max_ramp is None else max(max_ramp, ramp)
        previous = value
    return max_ramp


def compute_power_stats(
    buckets: list[TimeBucket],
    bucket_minutes: int,
    sustained_window_minutes: int,
    burst_window_minutes: int,
    sustained_percentile: float = 95,
    burst_percentile: float = 99,
) -> PowerStats:
    values = [bucket.cabinet_power_kw for bucket in buckets]
    present = [float(value) for value in values if value is not None]
    sustained_size = max(1, sustained_window_minutes // bucket_minutes)
    burst_size = max(1, burst_window_minutes // bucket_minutes)
    sustained_roll = rolling_averages(values, sustained_size)
    burst_roll = rolling_averages(values, burst_size)

    feed_a_values = [bucket.feed_power_kw.get("A") for bucket in buckets]
    feed_b_values = [bucket.feed_power_kw.get("B") for bucket in buckets]
    feed_a_present = [float(value) for value in feed_a_values if value is not None]
    feed_b_present = [float(value) for value in feed_b_values if value is not None]
    feed_a_p95 = percentile(feed_a_present, 95) if feed_a_present else None
    feed_b_p95 = percentile(feed_b_present, 95) if feed_b_present else None
    imbalance = None
    if feed_a_p95 is not None and feed_b_p95 is not None:
        average_feed = (feed_a_p95 + feed_b_p95) / 2.0
        if average_feed > 0:
            imbalance = abs(feed_a_p95 - feed_b_p95) / average_feed * 100.0

    return PowerStats(
        observed_power_min_kw=round_float(min(present), 3) if present else None,
        observed_power_p50_kw=round_float(percentile(present, 50), 3),
        observed_power_p95_kw=round_float(percentile(present, 95), 3),
        observed_power_p99_kw=round_float(percentile(present, 99), 3),
        observed_power_max_kw=round_float(max(present), 3) if present else None,
        observed_sustained_p95_kw=round_float(percentile(sustained_roll, sustained_percentile), 3),
        observed_short_burst_p99_kw=round_float(percentile(burst_roll, burst_percentile), 3),
        observed_short_burst_max_kw=round_float(max(burst_roll), 3) if burst_roll else None,
        observed_power_ramp_max_kw_per_min=round_float(max_ramp_per_min(values, bucket_minutes), 3),
        feed_imbalance_pct=round_float(imbalance, 3),
        feed_a_p95_kw=round_float(feed_a_p95, 3),
        feed_b_p95_kw=round_float(feed_b_p95, 3),
    )


def compute_temperature_stats(
    buckets: list[TimeBucket],
    bucket_minutes: int,
    require_top_middle_bottom: bool,
    hotspot_delta_top_bottom_c: float,
) -> TemperatureStats:
    values = [bucket.max_inlet_temp_c for bucket in buckets]
    present = [float(value) for value in values if value is not None]
    top_values = [bucket.top_inlet_temp_c for bucket in buckets if bucket.top_inlet_temp_c is not None]
    middle_values = [bucket.middle_inlet_temp_c for bucket in buckets if bucket.middle_inlet_temp_c is not None]
    bottom_values = [bucket.bottom_inlet_temp_c for bucket in buckets if bucket.bottom_inlet_temp_c is not None]
    reason_codes: list[str] = []
    missing_data: list[str] = []

    if top_values and middle_values and bottom_values:
        add_unique(reason_codes, "TOP_MIDDLE_BOTTOM_SENSORS_PRESENT")
    else:
        if not top_values:
            add_unique(reason_codes, "MISSING_TOP_INLET_SENSOR")
            add_unique(missing_data, "MISSING_TOP_INLET_SENSOR")
        if not middle_values:
            add_unique(reason_codes, "MISSING_MIDDLE_INLET_SENSOR")
            add_unique(missing_data, "MISSING_MIDDLE_INLET_SENSOR")
        if not bottom_values:
            add_unique(reason_codes, "MISSING_BOTTOM_INLET_SENSOR")
            add_unique(missing_data, "MISSING_BOTTOM_INLET_SENSOR")

    top_max = max(top_values) if top_values else None
    middle_max = max(middle_values) if middle_values else None
    bottom_max = max(bottom_values) if bottom_values else None
    hotspot_delta = None
    if top_max is not None and bottom_max is not None:
        hotspot_delta = top_max - bottom_max
        if hotspot_delta >= hotspot_delta_top_bottom_c:
            add_unique(reason_codes, "HOTSPOT_TOP_INLET")

    if require_top_middle_bottom:
        for code in ("MISSING_TOP_INLET_SENSOR", "MISSING_MIDDLE_INLET_SENSOR", "MISSING_BOTTOM_INLET_SENSOR"):
            if code in reason_codes:
                add_unique(missing_data, code)

    return TemperatureStats(
        observed_inlet_min_c=round_float(min(present), 3) if present else None,
        observed_inlet_p50_c=round_float(percentile(present, 50), 3),
        observed_inlet_p95_c=round_float(percentile(present, 95), 3),
        observed_inlet_p99_c=round_float(percentile(present, 99), 3),
        observed_inlet_max_c=round_float(max(present), 3) if present else None,
        observed_top_inlet_max_c=round_float(top_max, 3),
        observed_middle_inlet_max_c=round_float(middle_max, 3),
        observed_bottom_inlet_max_c=round_float(bottom_max, 3),
        observed_temp_ramp_max_c_per_min=round_float(max_ramp_per_min(values, bucket_minutes), 3),
        hotspot_delta_top_bottom_c=round_float(hotspot_delta, 3),
        reason_codes=reason_codes,
        missing_data=missing_data,
    )
