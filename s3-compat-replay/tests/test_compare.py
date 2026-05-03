from __future__ import annotations

from s3_compat_replay.compare import compare_step
from s3_compat_replay.models import Probe


def test_compares_status_code_mismatches():
    probe = Probe(id="p", family="object_read", required=True)
    mismatches = compare_step(probe, "HeadObject", {"status": 200}, {"status_code": 404, "headers": {}})
    assert mismatches[0].mismatch_code == "STATUS_CODE_MISMATCH"
    assert mismatches[0].severity == "BLOCKER"


def test_compares_s3_error_code_mismatches():
    probe = Probe(id="p", family="object_read", required=True)
    mismatches = compare_step(probe, "HeadObject", {"status": 404, "error_code": "NoSuchKey"}, {"status_code": 404, "error_code": "NotFound", "headers": {}})
    assert any(m.mismatch_code == "ERROR_CODE_MISMATCH" for m in mismatches)


def test_ignores_request_id_differences():
    probe = Probe(id="p", family="object_read", required=True)
    mismatches = compare_step(
        probe,
        "GetObject",
        {"status": 200},
        {"status_code": 200, "headers": {"x-amz-request-id": "different"}, "data": {"RequestId": "different"}},
    )
    assert mismatches == []
