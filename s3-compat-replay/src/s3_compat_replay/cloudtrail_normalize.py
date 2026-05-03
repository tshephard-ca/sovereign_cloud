from __future__ import annotations

import json
import re
from typing import Any

from .models import CloudTrailEvent, KeyShape, NormalizedS3Event
from .redact import stable_hash


FAMILY_BY_EVENT: dict[str, str] = {
    "GetObject": "object_read",
    "HeadObject": "object_read",
    "GetObjectAttributes": "object_read",
    "PutObject": "object_write",
    "CopyObject": "object_write",
    "RestoreObject": "object_write",
    "DeleteObject": "object_delete",
    "DeleteObjects": "object_delete",
    "ListObjects": "object_list",
    "ListObjectsV2": "object_list",
    "ListObjectVersions": "object_list",
    "CreateMultipartUpload": "multipart",
    "UploadPart": "multipart",
    "UploadPartCopy": "multipart",
    "CompleteMultipartUpload": "multipart",
    "AbortMultipartUpload": "multipart",
    "ListParts": "multipart",
    "ListMultipartUploads": "multipart",
    "GetObjectTagging": "tagging",
    "PutObjectTagging": "tagging",
    "DeleteObjectTagging": "tagging",
    "GetObjectAcl": "acl",
    "PutObjectAcl": "acl",
    "GetBucketAcl": "acl",
    "PutBucketAcl": "acl",
    "GetBucketVersioning": "versioning",
    "PutBucketVersioning": "versioning",
    "GetBucketCors": "cors",
    "PutBucketCors": "cors",
    "PutObjectRetention": "object_lock",
    "GetObjectRetention": "object_lock",
    "PutObjectLegalHold": "object_lock",
    "GetObjectLegalHold": "object_lock",
    "GetObjectLockConfiguration": "object_lock",
    "PutObjectLockConfiguration": "object_lock",
}

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
DATE_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
MONTH_RE = re.compile(r"^(0[1-9]|1[0-2])$")
NUMERIC_RE = re.compile(r"^\d+$")
ARN_RE = re.compile(r"^arn:[^:]*:s3:::(?P<bucket>[^/]+)(?:/(?P<key>.*))?$")


def classify_event(event_name: str | None, request_parameters: dict[str, Any] | None = None) -> str:
    if not event_name:
        return "unknown"
    family = FAMILY_BY_EVENT.get(event_name, "unknown")
    request_parameters = request_parameters or {}
    if family == "unknown" and "versionId" in request_parameters:
        return "versioning"
    if family in {"object_read", "object_write", "object_delete", "object_list"} and "versionId" in request_parameters:
        return "versioning"
    return family


def extract_bucket(event: CloudTrailEvent, enable_bucket_from_host: bool = False) -> str | None:
    params = event.requestParameters or {}
    for name in ("bucketName", "bucket"):
        value = params.get(name)
        if isinstance(value, str) and value:
            return value
    for resource in event.resources or []:
        arn = str(resource.get("ARN") or resource.get("arn") or "")
        parsed = ARN_RE.match(arn)
        if parsed:
            return parsed.group("bucket")
    host = params.get("host")
    if enable_bucket_from_host and isinstance(host, str) and host.count(".") >= 2:
        first = host.split(".", 1)[0]
        if first and first not in {"s3", "object"}:
            return first
    return None


def extract_key(event: CloudTrailEvent) -> str | None:
    params = event.requestParameters or {}
    value = params.get("key")
    if isinstance(value, str) and value:
        return value
    for resource in event.resources or []:
        arn = str(resource.get("ARN") or resource.get("arn") or "")
        parsed = ARN_RE.match(arn)
        if parsed and parsed.group("key"):
            return parsed.group("key")
    prefix = params.get("prefix")
    if isinstance(prefix, str) and prefix:
        return prefix
    return None


def _length_bucket(length: int) -> str:
    if length <= 32:
        return "0-32"
    if length <= 128:
        return "33-128"
    if length <= 512:
        return "129-512"
    return "513+"


def _segment_template(segment: str, redact: bool) -> tuple[str, dict[str, bool]]:
    flags = {"date": False, "uuid": False, "numeric": False}
    if UUID_RE.match(segment):
        flags["uuid"] = True
        return "{uuid}", flags
    if DATE_YEAR_RE.match(segment):
        flags["date"] = True
        return "{yyyy}", flags
    if MONTH_RE.match(segment):
        flags["date"] = True
        return "{mm}", flags
    dot = segment.rfind(".")
    stem = segment[:dot] if dot > 0 else segment
    ext = segment[dot:] if dot > 0 else ""
    if NUMERIC_RE.match(stem) or re.search(r"\d{3,}", stem):
        flags["numeric"] = True
        return "{id}" + ext.lower(), flags
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", segment)
    if redact:
        return "{segment}" + ext.lower() if ext else "{segment}", flags
    return safe, flags


def key_shape_for(key: str | None, redact: bool = False, hash_length: int = 12) -> KeyShape | None:
    if not key:
        return None
    segments = key.split("/")
    rendered: list[str] = []
    has_date = False
    has_uuid = False
    has_numeric = False
    for segment in segments:
        template, flags = _segment_template(segment, redact=redact)
        rendered.append(template)
        has_date = has_date or flags["date"]
        has_uuid = has_uuid or flags["uuid"]
        has_numeric = has_numeric or flags["numeric"]
    extension = None
    leaf = segments[-1]
    dot = leaf.rfind(".")
    if dot > 0 and dot < len(leaf) - 1:
        extension = leaf[dot:].lower()
    return KeyShape(
        slash_depth=key.count("/"),
        extension=extension,
        has_date_path=has_date,
        has_uuid_like_segment=has_uuid,
        has_numeric_id_segment=has_numeric,
        prefix_template="/".join(rendered),
        key_length_bucket=_length_bucket(len(key)),
        original_key_hash=stable_hash(key, hash_length),
    )


def event_shape_hash(event: NormalizedS3Event) -> str:
    shape = {
        "event_name": event.event_name,
        "family": event.operation_family,
        "request_keys": sorted(event.request_parameters.keys()),
        "has_version": "versionId" in event.request_parameters,
        "has_error": bool(event.error_code),
        "key_shape": event.key_shape.prefix_template if event.key_shape else None,
    }
    return stable_hash(json.dumps(shape, sort_keys=True), 16)


def detect_features(event: CloudTrailEvent, family: str) -> tuple[list[str], list[str]]:
    params = event.requestParameters or {}
    additional = event.additionalEventData or {}
    combined = json.dumps({"request": params, "additional": additional}, sort_keys=True).lower()
    features: set[str] = set()
    risk_flags: set[str] = set()
    if "versionId" in params or family == "versioning":
        features.add("VERSION_ID")
    if family == "multipart":
        features.add("MULTIPART")
    if family == "tagging" or "tagging" in combined or "tagset" in combined:
        features.add("OBJECT_TAGGING")
    if family == "acl" or "acl" in combined:
        features.add("ACL")
    if family == "object_lock" or "retention" in combined or "legalhold" in combined or "legal-hold" in combined:
        features.add("OBJECT_LOCK")
        risk_flags.add("OBJECT_LOCK_REQUIRES_BUCKET_SUPPORT")
    if family == "cors":
        features.add("CORS")
        risk_flags.add("CORS_REQUIRES_HTTP_PROBE")
    if "sse" in combined or "server-side-encryption" in combined or "x-amz-server-side-encryption" in combined:
        features.add("ENCRYPTION_HEADERS")
    if "sigv4" in combined or "signatureversion" in combined or "signature version" in combined:
        features.add("SIGNATURE_VERSION_OBSERVED")
    if "presigned" in combined or "query-string" in combined or "querystring" in combined:
        features.add("PRESIGNED_OBSERVED")
    return sorted(features), sorted(risk_flags)


def normalize_event(
    event: CloudTrailEvent,
    source_bucket: str,
    allowed_event_sources: set[str],
    enable_bucket_from_host: bool = False,
    redact: bool = False,
    hash_length: int = 12,
) -> NormalizedS3Event | None:
    if event.eventSource not in allowed_event_sources:
        return None
    bucket = extract_bucket(event, enable_bucket_from_host=enable_bucket_from_host)
    if bucket != source_bucket:
        return None
    key = extract_key(event)
    params = event.requestParameters or {}
    response = event.responseElements or {}
    additional = event.additionalEventData or {}
    family = classify_event(event.eventName, params)
    features, risk_flags = detect_features(event, family)
    warnings: list[str] = []
    if not event.requestParameters:
        warnings.append("CLOUDTRAIL_PARAMS_TRUNCATED")
    if event.responseElements is None:
        warnings.append("CLOUDTRAIL_RESPONSE_ELEMENTS_MISSING")
    if event.eventName is None or event.eventSource is None:
        warnings.append("CLOUDTRAIL_PARAMS_TRUNCATED")
    normalized = NormalizedS3Event(
        event_time=event.eventTime,
        event_source=event.eventSource,
        event_name=event.eventName,
        region=event.region,
        source_ip=None if redact else event.sourceIPAddress,
        user_agent=event.userAgent,
        bucket=bucket,
        key=None if redact else key,
        key_shape=key_shape_for(key, redact=redact, hash_length=hash_length),
        operation_family=family,
        request_parameters=params,
        response_elements=response,
        additional_event_data=additional,
        error_code=event.errorCode,
        error_message=event.errorMessage,
        read_only=_coerce_bool(event.readOnly),
        resources=event.resources or [],
        recipient_account_id=None if redact else event.recipientAccountId,
        request_id=event.requestID,
        event_id=event.eventID,
        observed_features=features,
        risk_flags=risk_flags,
        warnings=warnings,
    )
    normalized.source_shape_hash = event_shape_hash(normalized)
    return normalized


def _coerce_bool(value: bool | str | None) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return None


def sort_events(events: list[NormalizedS3Event]) -> list[NormalizedS3Event]:
    return sorted(events, key=lambda e: (e.event_time or "", e.event_id or "", e.request_id or ""))
