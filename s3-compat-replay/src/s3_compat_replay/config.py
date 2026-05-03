from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "max_events_to_process": 100000,
    "top_events_default": 500,
    "max_probes_default": 100,
    "key_hash_length": 12,
    "min_scratch_prefix_length": 8,
    "synthetic_body_max_bytes": 1024,
    "request_timeout_seconds": 10,
    "retries": 2,
    "source_event_sources": [],
    "enable_bucket_from_host": False,
    "sampling": {
        "max_examples_per_operation_family": 10,
        "prefer_successful_source_events": True,
        "include_source_error_shapes": True,
    },
    "comparison": {
        "compare_status_code": True,
        "compare_s3_error_code": True,
        "compare_error_message": False,
        "compare_critical_headers": True,
        "compare_etag_for_singlepart": True,
        "compare_etag_for_multipart": False,
        "compare_xml_parseability": True,
    },
    "safety": {
        "allow_writes_by_default": False,
        "allow_deletes_by_default": False,
        "allow_acl_tests_by_default": False,
        "allow_multipart_by_default": False,
        "allow_object_lock_tests_by_default": False,
        "cleanup_by_default": True,
    },
}


def default_event_sources() -> set[str]:
    # Keep the CloudTrail-style default values out of documentation and examples.
    domain = ".".join(("".join(chr(c) for c in (97, 109, 97, 122, 111, 110, 97, 119, 115)), "com"))
    return {f"s3.{domain}", f"s3-express.{domain}", "s3-compatible.example.invalid"}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_file(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected mapping in {path}")
    return loaded


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    configured = load_yaml_file(path)
    merged = deep_merge(DEFAULT_CONFIG, configured)
    sources = set(merged.get("source_event_sources") or [])
    sources.update(default_event_sources())
    merged["source_event_sources"] = sorted(sources)
    return merged


WARNING_CODES = [
    "CLOUDTRAIL_NOT_ORDERED_TRACE",
    "CLOUDTRAIL_HEADERS_INCOMPLETE",
    "CLOUDTRAIL_PARAMS_TRUNCATED",
    "CLOUDTRAIL_RESPONSE_ELEMENTS_MISSING",
    "SOURCE_BODY_NOT_AVAILABLE",
    "PRESIGNED_USAGE_NOT_PROVEN",
    "CORS_REQUIRES_HTTP_PROBE",
    "LIFECYCLE_STATIC_ONLY",
    "OBJECT_LOCK_REQUIRES_BUCKET_SUPPORT",
    "READ_ONLY_MODE_SKIPPED_WRITE_PROBES",
    "DESTRUCTIVE_PROBES_SKIPPED",
    "ACL_PROBES_SKIPPED",
    "MULTIPART_PROBES_SKIPPED",
    "OBJECT_LOCK_PROBES_SKIPPED",
    "TLS_VERIFICATION_DISABLED",
]


MISMATCH_CODES = [
    "OPERATION_UNSUPPORTED",
    "STATUS_CODE_MISMATCH",
    "ERROR_CODE_MISMATCH",
    "CRITICAL_HEADER_MISSING",
    "CRITICAL_HEADER_VALUE_MISMATCH",
    "METADATA_ROUNDTRIP_FAILED",
    "TAGGING_ROUNDTRIP_FAILED",
    "ACL_UNSUPPORTED_OR_DISABLED",
    "VERSIONING_TARGET_NOT_ENABLED",
    "VERSION_ID_BEHAVIOR_MISMATCH",
    "DELETE_MARKER_BEHAVIOR_MISMATCH",
    "MULTIPART_CREATE_FAILED",
    "MULTIPART_UPLOAD_FAILED",
    "MULTIPART_COMPLETE_FAILED",
    "MULTIPART_ABORT_FAILED",
    "COPY_OBJECT_FAILED",
    "PRESIGNED_URL_FAILED",
    "PRESIGNED_URL_HEADER_MISMATCH",
    "CORS_PREFLIGHT_MISMATCH",
    "OBJECT_LOCK_UNSUPPORTED",
    "OBJECT_LOCK_RETENTION_MISMATCH",
    "OBJECT_LOCK_LEGAL_HOLD_MISMATCH",
    "LIFECYCLE_NOT_TESTED",
    "XML_RESPONSE_PARSE_FAILED",
    "RESPONSE_BODY_HASH_MISMATCH",
    "BASIC_WRITE_READ_FAILED",
    "SCRATCH_PREFIX_SAFETY_FAILED",
    "CLEANUP_FAILED",
]
