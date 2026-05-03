from __future__ import annotations

from s3_compat_replay.bucket_config import load_bucket_config
from s3_compat_replay.cloudtrail_normalize import normalize_event, sort_events
from s3_compat_replay.config import load_config
from s3_compat_replay.models import CloudTrailEvent
from s3_compat_replay.request_hints import load_request_hints
from s3_compat_replay.usage_profile import build_usage_profile

from conftest import make_event


def _profile(records, redact=False, hints=None, bucket_config=None):
    cfg = load_config(None)
    normalized = [
        event
        for event in (
            normalize_event(CloudTrailEvent(**{**raw, "raw": raw}), "source-bucket-example", set(cfg["source_event_sources"]), redact=redact)
            for raw in records
        )
        if event
    ]
    return build_usage_profile("source-bucket-example", len(records), sort_events(normalized), request_hints=hints, bucket_config=bucket_config)


def test_usage_profile_counts_families_and_warnings():
    profile = _profile([make_event("GetObject"), make_event("HeadObject"), make_event("PutObject")])
    assert profile.processed_event_count == 3
    assert profile.operation_families["object_read"].count == 2
    assert profile.operation_families["object_write"].count == 1
    assert "CLOUDTRAIL_NOT_ORDERED_TRACE" in profile.warnings


def test_marks_presigned_from_request_hints(tmp_path):
    path = tmp_path / "request-hints.yml"
    path.write_text("presigned:\n  observed: true\n  methods: [GET]\n", encoding="utf-8")
    profile = _profile([make_event("GetObject")], hints=load_request_hints(path))
    assert "PRESIGNED_OBSERVED" in profile.observed_features
    assert "PRESIGNED_OBSERVED" in profile.request_hint_features


def test_bucket_config_features_are_reported(tmp_path):
    path = tmp_path / "bucket-config.yml"
    path.write_text("versioning:\n  status: Enabled\nlifecycle:\n  rules: []\n", encoding="utf-8")
    profile = _profile([make_event("GetObject")], bucket_config=load_bucket_config(path))
    assert "VERSIONING" in profile.bucket_config_features
    assert "LIFECYCLE" in profile.bucket_config_features
    assert "LIFECYCLE_STATIC_ONLY" in profile.warnings


def test_key_shapes_do_not_expose_original_key_when_redacted():
    profile = _profile([make_event("GetObject", key="private/customer-12345/report.pdf")], redact=True)
    shape = profile.key_shapes[0]
    assert "private" not in shape.prefix_template
    assert "customer" not in shape.prefix_template
    assert shape.extension == ".pdf"
    assert len(shape.original_key_hash) == 12
