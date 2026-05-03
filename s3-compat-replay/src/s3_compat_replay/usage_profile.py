from __future__ import annotations

from collections import Counter, defaultdict

from .bucket_config import bucket_config_features
from .models import (
    BucketConfig,
    EvidenceQuality,
    KeyShape,
    NormalizedS3Event,
    OperationFamilyProfile,
    RequestHints,
    TimeRange,
    UsageProfile,
)
from .request_hints import request_hint_features


BASE_ANALYSIS_WARNINGS = [
    "CLOUDTRAIL_NOT_ORDERED_TRACE",
    "CLOUDTRAIL_HEADERS_INCOMPLETE",
    "SOURCE_BODY_NOT_AVAILABLE",
]


def build_usage_profile(
    source_bucket: str,
    event_count: int,
    processed_events: list[NormalizedS3Event],
    request_hints: RequestHints | None = None,
    bucket_config: BucketConfig | None = None,
) -> UsageProfile:
    operation_families: dict[str, OperationFamilyProfile] = {}
    family_events: dict[str, list[NormalizedS3Event]] = defaultdict(list)
    for event in processed_events:
        family_events[event.operation_family].append(event)

    for family in sorted(family_events):
        events = family_events[family]
        event_names = Counter(event.event_name or "UNKNOWN" for event in events)
        features = sorted({feature for event in events for feature in event.observed_features})
        sample_ids = [
            event.event_id or event.request_id or event.source_shape_hash or "unknown"
            for event in events[:10]
        ]
        operation_families[family] = OperationFamilyProfile(
            count=len(events),
            event_names=dict(sorted(event_names.items())),
            observed_features=features,
            sample_event_ids=sample_ids,
        )

    request_features = request_hint_features(request_hints or RequestHints())
    bucket_features = bucket_config_features(bucket_config or BucketConfig())
    observed_features = sorted(
        {feature for event in processed_events for feature in event.observed_features}
        | set(request_features)
        | set(bucket_features)
    )

    warnings = set(BASE_ANALYSIS_WARNINGS)
    for event in processed_events:
        warnings.update(event.warnings)
        warnings.update(event.risk_flags)
    if not any(event.response_elements for event in processed_events):
        warnings.add("CLOUDTRAIL_RESPONSE_ELEMENTS_MISSING")
    if any(not event.request_parameters for event in processed_events):
        warnings.add("CLOUDTRAIL_PARAMS_TRUNCATED")
    if "PRESIGNED_OBSERVED" not in observed_features:
        warnings.add("PRESIGNED_USAGE_NOT_PROVEN")
    if "CORS" in observed_features:
        warnings.add("CORS_REQUIRES_HTTP_PROBE")
    if "LIFECYCLE" in observed_features:
        warnings.add("LIFECYCLE_STATIC_ONLY")
    if "OBJECT_LOCK" in observed_features:
        warnings.add("OBJECT_LOCK_REQUIRES_BUCKET_SUPPORT")

    sorted_events = sorted(processed_events, key=lambda e: (e.event_time or "", e.event_id or "", e.request_id or ""))
    first = sorted_events[0].event_time if sorted_events else None
    last = sorted_events[-1].event_time if sorted_events else None
    key_shapes = _unique_key_shapes([event.key_shape for event in processed_events if event.key_shape])
    request_shapes = _request_shapes(processed_events)
    quality = EvidenceQuality(
        has_request_parameters=any(bool(event.request_parameters) for event in processed_events),
        has_response_elements=any(bool(event.response_elements) for event in processed_events),
        has_additional_event_data=any(bool(event.additional_event_data) for event in processed_events),
        has_errors=any(bool(event.error_code) for event in processed_events),
        truncated_or_missing_fields=any(not event.request_parameters or "CLOUDTRAIL_PARAMS_TRUNCATED" in event.warnings for event in processed_events),
    )
    return UsageProfile(
        source_bucket=source_bucket,
        event_count=event_count,
        processed_event_count=len(processed_events),
        ignored_event_count=max(event_count - len(processed_events), 0),
        time_range=TimeRange(first_event_time=first, last_event_time=last),
        operation_families=operation_families,
        observed_features=observed_features,
        key_shapes=key_shapes,
        user_agents=sorted({event.user_agent for event in processed_events if event.user_agent}),
        request_shapes=request_shapes,
        risk_flags=sorted({flag for event in processed_events for flag in event.risk_flags}),
        warnings=sorted(warnings),
        evidence_quality=quality,
        request_hint_features=request_features,
        bucket_config_features=bucket_features,
    )


def _unique_key_shapes(shapes: list[KeyShape]) -> list[KeyShape]:
    by_key: dict[tuple[str, str | None, int], KeyShape] = {}
    for shape in shapes:
        key = (shape.prefix_template, shape.extension, shape.slash_depth)
        by_key.setdefault(key, shape)
    return [by_key[key] for key in sorted(by_key)]


def _request_shapes(events: list[NormalizedS3Event]) -> list[dict[str, object]]:
    seen: set[tuple[str, tuple[str, ...], str | None]] = set()
    output: list[dict[str, object]] = []
    for event in sorted(events, key=lambda e: (e.operation_family, e.event_name or "", e.source_shape_hash or "")):
        key = (event.event_name or "UNKNOWN", tuple(sorted(event.request_parameters.keys())), event.key_shape.prefix_template if event.key_shape else None)
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "event_name": key[0],
                "operation_family": event.operation_family,
                "request_parameter_keys": list(key[1]),
                "key_shape": key[2],
                "source_shape_hash": event.source_shape_hash,
            }
        )
    return output


def confidence_from_profile(profile: UsageProfile, target_probe_ran: bool = True) -> str:
    if profile.processed_event_count < 5 or not target_probe_ran:
        return "LOW"
    if profile.evidence_quality.truncated_or_missing_fields:
        return "MEDIUM"
    if profile.evidence_quality.has_request_parameters and profile.evidence_quality.has_additional_event_data:
        return "HIGH"
    return "MEDIUM"
