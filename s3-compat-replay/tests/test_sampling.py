from __future__ import annotations

from s3_compat_replay.cloudtrail_normalize import normalize_event, sort_events
from s3_compat_replay.config import load_config
from s3_compat_replay.models import CloudTrailEvent
from s3_compat_replay.sample_events import sample_by_shape

from conftest import make_event


def _events(records):
    cfg = load_config(None)
    return sort_events(
        [
            event
            for event in (
                normalize_event(CloudTrailEvent(**{**raw, "raw": raw}), "source-bucket-example", set(cfg["source_event_sources"]))
                for raw in records
            )
            if event
        ]
    )


def test_sampling_is_by_shape_not_order_only():
    records = [
        make_event("GetObject", key="docs/2026/01/a.pdf", eventTime="2026-01-01T00:01:00Z"),
        make_event("PutObject", key="docs/2026/01/b.pdf", eventTime="2026-01-01T00:00:00Z"),
    ]
    sampled = sample_by_shape(_events(records), limit=10)
    assert [event.operation_family for event in sampled] == ["object_read", "object_write"]


def test_sampling_prefers_successful_event_for_same_shape():
    failed = make_event("GetObject", errorCode="NoSuchKey")
    ok = make_event("GetObject")
    sampled = sample_by_shape(_events([failed, ok]), limit=10)
    assert sampled[0].error_code is None
