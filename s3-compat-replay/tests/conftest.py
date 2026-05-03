from __future__ import annotations

import gzip
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest


EVENT_SOURCE = "s3-compatible.example.invalid"


def make_event(event_name: str = "GetObject", bucket: str = "source-bucket-example", key: str | None = "docs/2026/01/customer-123.pdf", **overrides):
    event = {
        "eventVersion": "1.09",
        "eventTime": "2026-01-01T00:00:00Z",
        "eventSource": EVENT_SOURCE,
        "eventName": event_name,
        "region": "us-east-1",
        "sourceIPAddress": "192.0.2.1",
        "userAgent": "test-sdk/1.0",
        "requestParameters": {"bucketName": bucket},
        "responseElements": {},
        "additionalEventData": {"SignatureVersion": "SigV4"},
        "readOnly": event_name.startswith(("Get", "Head", "List")),
        "requestID": f"req-{event_name}",
        "eventID": f"event-{event_name}",
    }
    if key is not None:
        event["requestParameters"]["key"] = key
        event["resources"] = [{"ARN": f"arn:example:s3:::{bucket}/{key}"}]
    else:
        event["resources"] = [{"ARN": f"arn:example:s3:::{bucket}"}]
    for key_name, value in overrides.items():
        if key_name == "requestParameters":
            event["requestParameters"] = value
        else:
            event[key_name] = value
    return event


def write_records(path: Path, records: list[dict]) -> Path:
    path.write_text(json.dumps({"Records": records}), encoding="utf-8")
    return path


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    return path


def write_gz(path: Path, records: list[dict]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump({"Records": records}, handle)
    return path


class FakeS3Client:
    def __init__(self, fail_cleanup: bool = False, fail_status: dict[str, int] | None = None) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.headers: dict[tuple[str, str], dict[str, str]] = {}
        self.tags: dict[tuple[str, str], dict[str, str]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_cleanup = fail_cleanup
        self.fail_status = fail_status or {}

    def _status(self, op: str, default: int) -> int:
        return self.fail_status.get(op, default)

    def put_object(self, bucket, key, body, content_type=None, metadata=None, tagging=None):
        self.calls.append(("PutObject", {"bucket": bucket, "key": key, "tagging": tagging}))
        self.objects[(bucket, key)] = body
        self.headers[(bucket, key)] = {"Content-Type": content_type or "binary/octet-stream"}
        return {"status_code": self._status("PutObject", 200), "error_code": None, "headers": {}, "data": {}}

    def head_object(self, bucket, key):
        self.calls.append(("HeadObject", {"bucket": bucket, "key": key}))
        if (bucket, key) not in self.objects:
            return {"status_code": 404, "error_code": "NoSuchKey", "headers": {}, "data": {}}
        return {"status_code": self._status("HeadObject", 200), "error_code": None, "headers": self.headers[(bucket, key)], "data": {}}

    def get_object(self, bucket, key):
        self.calls.append(("GetObject", {"bucket": bucket, "key": key}))
        return {"status_code": self._status("GetObject", 200), "error_code": None, "headers": self.headers.get((bucket, key), {}), "body": self.objects.get((bucket, key), b""), "data": {}}

    def delete_object(self, bucket, key):
        self.calls.append(("DeleteObject", {"bucket": bucket, "key": key}))
        if self.fail_cleanup:
            return {"status_code": 500, "error_code": "CleanupFailed", "headers": {}, "data": {}}
        self.objects.pop((bucket, key), None)
        return {"status_code": 204, "error_code": None, "headers": {}, "data": {}}

    def list_objects_v2(self, bucket, prefix, delimiter=None, max_keys=1000, continuation_token=None):
        self.calls.append(("ListObjectsV2", {"bucket": bucket, "prefix": prefix, "delimiter": delimiter, "max_keys": max_keys}))
        keys = [key for b, key in self.objects if b == bucket and key.startswith(prefix)]
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {"Contents": [{"Key": key} for key in keys]}}

    def copy_object(self, bucket, key, copy_source):
        self.calls.append(("CopyObject", {"bucket": bucket, "key": key, "copy_source": copy_source}))
        source_key = copy_source["Key"]
        self.objects[(bucket, key)] = self.objects[(bucket, source_key)]
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {}}

    def put_object_tagging(self, bucket, key, tags):
        self.calls.append(("PutObjectTagging", {"bucket": bucket, "key": key, "tags": tags}))
        self.tags[(bucket, key)] = tags
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {}}

    def get_object_tagging(self, bucket, key):
        self.calls.append(("GetObjectTagging", {"bucket": bucket, "key": key}))
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {"TagSet": [{"Key": k, "Value": v} for k, v in self.tags.get((bucket, key), {}).items()]}}

    def delete_object_tagging(self, bucket, key):
        self.calls.append(("DeleteObjectTagging", {"bucket": bucket, "key": key}))
        self.tags.pop((bucket, key), None)
        return {"status_code": 204, "error_code": None, "headers": {}, "data": {}}

    def get_object_acl(self, bucket, key):
        self.calls.append(("GetObjectAcl", {"bucket": bucket, "key": key}))
        return {"status_code": self._status("GetObjectAcl", 200), "error_code": None, "headers": {}, "data": {}}

    def get_bucket_versioning(self, bucket):
        self.calls.append(("GetBucketVersioning", {"bucket": bucket}))
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {"Status": "Enabled"}}

    def list_object_versions(self, bucket, prefix):
        self.calls.append(("ListObjectVersions", {"bucket": bucket, "prefix": prefix}))
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {"Versions": []}}

    def create_multipart_upload(self, bucket, key):
        self.calls.append(("CreateMultipartUpload", {"bucket": bucket, "key": key}))
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {"UploadId": "upload-1"}}

    def upload_part(self, bucket, key, upload_id, part_number, body):
        self.calls.append(("UploadPart", {"bucket": bucket, "key": key, "part_number": part_number}))
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {"ETag": "\"etag-1\""}}

    def complete_multipart_upload(self, bucket, key, upload_id, parts):
        self.calls.append(("CompleteMultipartUpload", {"bucket": bucket, "key": key, "parts": parts}))
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {}}

    def put_object_retention(self, bucket, key, mode, retain_until_date):
        self.calls.append(("PutObjectRetention", {"bucket": bucket, "key": key, "mode": mode}))
        return {"status_code": 200, "error_code": None, "headers": {}, "data": {}}

    def generate_presigned_url(self, method, bucket, key, expires_in):
        self.calls.append(("GeneratePresignedUrl", {"method": method, "bucket": bucket, "key": key, "expires_in": expires_in}))
        return f"https://target.example.invalid/{bucket}/{key}?X-Amz-Signature=secret&X-Amz-Credential=secret"

    def request_presigned(self, method, url, body=None):
        self.calls.append(("PresignedRequest", {"method": method, "path": urlsplit(url).path}))
        return {"status_code": 200, "error_code": None, "headers": {"Content-Type": "text/plain"}, "body": b"presigned", "data": {}}

    def cors_preflight(self, bucket, origin, method, request_headers):
        self.calls.append(("CorsPreflight", {"bucket": bucket, "origin": origin, "method": method, "request_headers": request_headers}))
        return {"status_code": 200, "error_code": None, "headers": {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": method, "Access-Control-Allow-Headers": ", ".join(request_headers)}, "data": {}}


@pytest.fixture()
def fake_client():
    return FakeS3Client()
