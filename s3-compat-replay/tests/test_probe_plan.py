from __future__ import annotations

from s3_compat_replay.bucket_config import load_bucket_config
from s3_compat_replay.cloudtrail_normalize import normalize_event, sort_events
from s3_compat_replay.config import load_config
from s3_compat_replay.models import CloudTrailEvent
from s3_compat_replay.probe_plan import build_probe_plan, plan_to_yaml
from s3_compat_replay.request_hints import load_request_hints
from s3_compat_replay.usage_profile import build_usage_profile

from conftest import make_event


def _profile(records):
    cfg = load_config(None)
    normalized = [
        event
        for event in (
            normalize_event(CloudTrailEvent(**{**raw, "raw": raw}), "source-bucket-example", set(cfg["source_event_sources"]))
            for raw in records
        )
        if event
    ]
    return build_usage_profile("source-bucket-example", len(records), sort_events(normalized))


def test_generates_deterministic_probe_plan_from_same_input():
    records = [make_event("GetObject"), make_event("ListObjectsV2", key=None, requestParameters={"bucketName": "source-bucket-example", "prefix": "docs/"})]
    p1 = build_probe_plan(_profile(records))
    p2 = build_probe_plan(_profile(records))
    assert plan_to_yaml(p1) == plan_to_yaml(p2)


def test_respects_max_probes():
    records = [
        make_event("GetObject"),
        make_event("ListObjectsV2", key=None, requestParameters={"bucketName": "source-bucket-example", "prefix": "docs/"}),
        make_event("PutObjectTagging"),
    ]
    plan = build_probe_plan(_profile(records), max_probes=1)
    assert len(plan.probes) == 1


def test_plan_marks_required_allow_flags(tmp_path):
    hints_path = tmp_path / "request-hints.yml"
    hints_path.write_text("object_lock:\n  retention_mode: GOVERNANCE\n", encoding="utf-8")
    bucket_path = tmp_path / "bucket.yml"
    bucket_path.write_text("versioning:\n  status: Enabled\n", encoding="utf-8")
    profile = _profile([make_event("DeleteObject"), make_event("GetObjectAcl"), make_event("CreateMultipartUpload")])
    plan = build_probe_plan(profile, request_hints=load_request_hints(hints_path), bucket_config=load_bucket_config(bucket_path))
    probes = {probe.id: probe for probe in plan.probes}
    assert probes["delete_synthetic_object"].requires_allow_deletes
    assert probes["acl_get_object"].requires_allow_acl_tests
    assert probes["multipart_upload_small"].requires_allow_multipart
    assert probes["object_lock_static_or_lab"].requires_allow_object_lock_tests
