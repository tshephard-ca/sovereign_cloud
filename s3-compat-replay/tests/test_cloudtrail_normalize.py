from __future__ import annotations

from s3_compat_replay.cloudtrail_normalize import classify_event, normalize_event
from s3_compat_replay.config import load_config
from s3_compat_replay.models import CloudTrailEvent

from conftest import EVENT_SOURCE, make_event


def _norm(raw, bucket="source-bucket-example", redact=False):
    return normalize_event(
        CloudTrailEvent(**{**raw, "raw": raw}),
        source_bucket=bucket,
        allowed_event_sources=set(load_config(None)["source_event_sources"]),
        redact=redact,
    )


def test_filters_events_by_source_bucket():
    assert _norm(make_event("GetObject", bucket="other-bucket")) is None
    assert _norm(make_event("GetObject")) is not None


def test_ignores_non_s3_events():
    raw = make_event("GetObject", eventSource="compute.example.invalid")
    assert _norm(raw) is None


def test_handles_missing_request_parameters():
    raw = make_event("GetObject", requestParameters=None)
    event = _norm(raw)
    assert event.bucket == "source-bucket-example"
    assert "CLOUDTRAIL_PARAMS_TRUNCATED" in event.warnings


def test_detects_truncated_or_omitted_fields():
    raw = make_event("GetObject")
    raw["requestParameters"] = {"bucketName": "source-bucket-example"}
    raw["responseElements"] = None
    event = _norm(raw)
    assert "CLOUDTRAIL_RESPONSE_ELEMENTS_MISSING" in event.warnings


def test_classifies_object_read_events():
    assert classify_event("GetObject") == "object_read"
    assert classify_event("HeadObject") == "object_read"


def test_classifies_object_write_events():
    assert classify_event("PutObject") == "object_write"
    assert classify_event("CopyObject") == "object_write"


def test_classifies_delete_list_multipart_tagging_acl():
    assert classify_event("DeleteObject") == "object_delete"
    assert classify_event("DeleteObjects") == "object_delete"
    assert classify_event("ListObjectsV2") == "object_list"
    assert classify_event("CreateMultipartUpload") == "multipart"
    assert classify_event("PutObjectTagging") == "tagging"
    assert classify_event("GetObjectAcl") == "acl"


def test_classifies_version_id_usage():
    event = _norm(make_event("GetObject", requestParameters={"bucketName": "source-bucket-example", "key": "a.txt", "versionId": "v1"}))
    assert event.operation_family == "versioning"
    assert "VERSION_ID" in event.observed_features


def test_does_not_mark_presigned_without_explicit_evidence():
    event = _norm(make_event("GetObject", additionalEventData={"SignatureVersion": "SigV4"}))
    assert "PRESIGNED_OBSERVED" not in event.observed_features
    assert "SIGNATURE_VERSION_OBSERVED" in event.observed_features


def test_marks_presigned_with_explicit_evidence():
    event = _norm(make_event("GetObject", additionalEventData={"authType": "REST-QUERY-STRING", "presigned": True}))
    assert "PRESIGNED_OBSERVED" in event.observed_features
