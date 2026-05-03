from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .bucket_config import load_bucket_config
from .cloudtrail_normalize import FAMILY_BY_EVENT
from .cloudtrail_parse import parse_cloudtrail
from .compare import make_mismatch
from .config import load_config
from .models import (
    GapFinding,
    ProbePlan,
    ProbeResult,
    ProbeResults,
    ProbeStepResult,
    RealWorldDataAssessment,
    RealWorldGeneratedFixture,
    UsageProfile,
)
from .probe_plan import plan_from_yaml
from .redact import stable_hash
from .report import build_summary, collect_mismatches, read_json, write_json, write_mismatches_csv
from .request_hints import load_request_hints


GENERIC_EVENT_SOURCE = "s3-compatible.example.invalid"
WORKLOAD_TYPES = ["application_upload_bucket", "public_assets", "backup_archive", "regulated_retention", "data_lake"]
FULL_FAMILIES = [
    "object_read",
    "object_write",
    "object_delete",
    "object_list",
    "multipart",
    "tagging",
    "acl",
    "versioning",
    "cors",
    "object_lock",
    "presigned",
    "encryption_headers",
]


def generate_real_world_fixture(output_dir: str | Path, *, source_bucket: str = "source-bucket-example", event_count: int = 180) -> RealWorldGeneratedFixture:
    output = Path(output_dir)
    cloudtrail_dir = output / "cloudtrail"
    cloudtrail_dir.mkdir(parents=True, exist_ok=True)
    events = _expand_events(_base_events(source_bucket), event_count)
    records_path = cloudtrail_dir / "s3-data-events.json"
    jsonl_path = cloudtrail_dir / "s3-data-events.jsonl"
    gzip_path = cloudtrail_dir / "s3-data-events.json.gz"
    first_cut = max(len(events) // 3, 1)
    second_cut = max((2 * len(events)) // 3, first_cut + 1)
    records_events = events[:first_cut]
    jsonl_events = events[first_cut:second_cut]
    gzip_events = events[second_cut:]
    records_payload = {"Records": records_events}
    records_path.write_text(json.dumps(records_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    jsonl_path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in jsonl_events) + "\n", encoding="utf-8")
    with gzip.open(gzip_path, "wt", encoding="utf-8") as handle:
        json.dump({"Records": gzip_events}, handle, sort_keys=True)
    hints_path = output / "request-hints.yml"
    bucket_config_path = output / "source-bucket-config.yml"
    business_context_path = output / "business-context.yml"
    http_trace_path = output / "sanitized-http-trace.jsonl"
    access_log_path = output / "server-access-log.jsonl"
    policy_context_path = output / "policy-context.yml"
    corpus_calibration_path = output / "corpus-calibration.yml"
    hints_path.write_text(yaml.safe_dump(_request_hints(), sort_keys=False), encoding="utf-8")
    bucket_config_path.write_text(yaml.safe_dump(_bucket_config(), sort_keys=False), encoding="utf-8")
    business_context_path.write_text(yaml.safe_dump(_business_context(), sort_keys=False), encoding="utf-8")
    http_trace_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in _http_trace(events[: min(len(events), 80)])) + "\n", encoding="utf-8")
    access_log_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in _server_access_log(events[: min(len(events), 80)])) + "\n", encoding="utf-8")
    policy_context_path.write_text(yaml.safe_dump(_policy_context(), sort_keys=False), encoding="utf-8")
    corpus_calibration_path.write_text(yaml.safe_dump(_corpus_calibration(), sort_keys=False), encoding="utf-8")
    return RealWorldGeneratedFixture(
        source_bucket=source_bucket,
        generated_at=_now(),
        event_count=len(events),
        files={
            "cloudtrail_records": str(records_path),
            "cloudtrail_jsonl": str(jsonl_path),
            "cloudtrail_gzip": str(gzip_path),
            "request_hints": str(hints_path),
            "bucket_config": str(bucket_config_path),
            "business_context": str(business_context_path),
            "http_trace": str(http_trace_path),
            "server_access_log": str(access_log_path),
            "policy_context": str(policy_context_path),
            "corpus_calibration": str(corpus_calibration_path),
        },
        workload_types=WORKLOAD_TYPES,
        operation_families=FULL_FAMILIES,
        intended_business_risks=[
            "Browser upload and download paths may fail if CORS or presigned URL behavior differs.",
            "Retention workflows may fail if Object Lock behavior is missing or not enabled.",
            "Application metadata and tag routing may fail if round trips are unsupported.",
            "Version-aware recovery or audit tooling may fail if version IDs or delete markers differ.",
            "Large ingest jobs may fail if multipart constraints differ.",
        ],
    )


def simulate_real_world_results(
    plan_path: str | Path,
    output_results: str | Path,
    output_mismatches: str | Path,
    *,
    endpoint_url: str = "https://endpoint_redacted",
    target_bucket: str = "bucket_002",
    scratch_prefix: str = "compat-replay/",
    scenario: str = "semantic-gaps",
) -> ProbeResults:
    plan = plan_from_yaml(Path(plan_path).read_text(encoding="utf-8"))
    started = _now()
    results: list[ProbeResult] = []
    for probe in plan.probes:
        result = ProbeResult(probe_id=probe.id, family=probe.family)
        if scenario == "all-pass":
            result.steps = [ProbeStepResult(operation=step.operation, status_code=_expected_status(step.expect), critical_headers={}, duration_ms=10) for step in [*probe.setup, *probe.steps]]
        else:
            result = _semantic_gap_result(probe)
        results.append(result)
    probes_failed = sum(1 for result in results if result.status == "FAIL")
    probes_skipped = sum(1 for result in results if result.status == "SKIP")
    output = ProbeResults(
        result_source="simulated_semantic_fixture" if scenario != "all-pass" else "simulated_all_pass_fixture",
        run_id=f"simulated-{stable_hash(plan.source_bucket + scenario, 12)}",
        endpoint_url_redacted=endpoint_url,
        target_bucket_redacted=target_bucket,
        scratch_prefix=scratch_prefix,
        started_at=started,
        finished_at=_now(),
        probes_run=len(results) - probes_skipped,
        probes_skipped=probes_skipped,
        probes_failed=probes_failed,
        cleanup={"attempted": True, "succeeded": True, "cleanup_manifest": None},
        results=results,
        warnings=sorted({warning for result in results for warning in result.warnings}),
    )
    write_json(output_results, output)
    write_mismatches_csv(output_mismatches, output)
    return output


def assess_real_world_data(
    *,
    cloudtrail_path: str | Path | None = None,
    request_hints_path: str | Path | None = None,
    bucket_config_path: str | Path | None = None,
    http_trace_path: str | Path | None = None,
    server_access_log_path: str | Path | None = None,
    policy_context_path: str | Path | None = None,
    business_context_path: str | Path | None = None,
    corpus_calibration_path: str | Path | None = None,
    profile_path: str | Path | None = None,
    plan_path: str | Path | None = None,
    results_path: str | Path | None = None,
    summary_path: str | Path | None = None,
    matrix_path: str | Path | None = None,
    questionnaire_path: str | Path | None = None,
) -> RealWorldDataAssessment:
    input_coverage = _input_coverage(
        cloudtrail_path,
        request_hints_path,
        bucket_config_path,
        http_trace_path=http_trace_path,
        server_access_log_path=server_access_log_path,
        policy_context_path=policy_context_path,
        business_context_path=business_context_path,
        corpus_calibration_path=corpus_calibration_path,
    )
    output_coverage = _output_coverage(
        profile_path,
        plan_path,
        results_path,
        summary_path,
        matrix_path=matrix_path,
        questionnaire_path=questionnaire_path,
        business_context_path=business_context_path,
    )
    business_findings = _business_findings(results_path, summary_path)
    input_gaps = _input_gaps(input_coverage)
    output_gaps = _output_gaps(output_coverage, results_path)
    status = "PASS" if input_coverage.get("family_coverage_percent", 0) >= 90 and output_coverage.get("plan_family_coverage_percent", 0) >= 70 and business_findings else "REVIEW"
    return RealWorldDataAssessment(
        status=status,
        input_coverage=input_coverage,
        output_coverage=output_coverage,
        business_impact_findings=business_findings,
        input_gaps=input_gaps,
        output_gaps=output_gaps,
        realism_notes=[
            "Generated input uses deterministic CloudTrail-style records with realistic operation mixes, errors, key shapes, and optional offline context.",
            "Generated output uses simulated target behavior, so it is appropriate for coverage and reporting validation but not for endpoint certification.",
            "Business impact is represented through blocker and review mismatches mapped to app-owner questions.",
        ],
    )


def assessment_markdown(assessment: RealWorldDataAssessment) -> str:
    lines = [
        "# Real-World Data Assessment",
        "",
        f"Status: **{assessment.status}**",
        "",
        "## Input Coverage",
        "",
    ]
    for key, value in sorted(assessment.input_coverage.items()):
        lines.extend(_coverage_markdown_lines(key, value))
    lines.extend(["", "## Output Coverage", ""])
    for key, value in sorted(assessment.output_coverage.items()):
        lines.extend(_coverage_markdown_lines(key, value))
    lines.extend(["", "## Business Impact Findings", ""])
    if assessment.business_impact_findings:
        for finding in assessment.business_impact_findings:
            lines.append(f"- {finding['severity']} {finding['code']}: {finding['business_impact']}")
    else:
        lines.append("- No business-impact findings were present.")
    lines.extend(["", "## Input Gaps", ""])
    lines.extend(_gap_lines(assessment.input_gaps))
    lines.extend(["", "## Output Gaps", ""])
    lines.extend(_gap_lines(assessment.output_gaps))
    lines.extend(["", "## Realism Notes", ""])
    lines.extend(f"- {note}" for note in assessment.realism_notes)
    return "\n".join(lines) + "\n"


def _coverage_markdown_lines(key: str, value: Any) -> list[str]:
    label = key.replace("_", " ")
    if isinstance(value, list):
        if not value:
            return [f"- {label}: none"]
        lines = [f"- {label}:"]
        lines.extend(f"  - {item}" for item in value)
        return lines
    if isinstance(value, dict):
        if not value:
            return [f"- {label}: none"]
        lines = [f"- {label}:"]
        for nested_key, nested_value in sorted(value.items()):
            lines.append(f"  - {str(nested_key).replace('_', ' ')}: {nested_value}")
        return lines
    return [f"- {label}: {value}"]


def _base_events(bucket: str) -> list[dict[str, Any]]:
    base_time = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    specs = [
        ("PutObject", "uploads/2026/01/customer-10001/profile.pdf", {"contentType": "application/pdf", "x-amz-meta-client-id": "client-10001", "x-amz-server-side-encryption": "AES256"}, False),
        ("HeadObject", "uploads/2026/01/customer-10001/profile.pdf", {}, True),
        ("GetObject", "uploads/2026/01/customer-10001/profile.pdf", {"Range": "bytes=0-1023"}, True),
        ("GetObjectAttributes", "uploads/2026/01/customer-10001/profile.pdf", {}, True),
        ("ListObjectsV2", None, {"prefix": "uploads/2026/01/", "delimiter": "/", "maxKeys": 1000}, True),
        ("ListObjectsV2", None, {"prefix": "uploads/2026/01/", "delimiter": "/", "maxKeys": 1, "continuationToken": "token-redacted"}, True),
        ("CopyObject", "processed/2026/01/customer-10001/profile.pdf", {"copySource": f"{bucket}/uploads/2026/01/customer-10001/profile.pdf"}, False),
        ("PutObjectTagging", "processed/2026/01/customer-10001/profile.pdf", {"tagging": "environment=test&app=orders&pii=false"}, False),
        ("GetObjectTagging", "processed/2026/01/customer-10001/profile.pdf", {}, True),
        ("DeleteObjectTagging", "processed/2026/01/customer-10001/profile.pdf", {}, False),
        ("GetObjectAcl", "processed/2026/01/customer-10001/profile.pdf", {}, True),
        ("PutObjectAcl", "processed/2026/01/customer-10001/profile.pdf", {"acl": "bucket-owner-full-control"}, False),
        ("GetBucketAcl", None, {}, True),
        ("GetBucketVersioning", None, {}, True),
        ("ListObjectVersions", None, {"prefix": "processed/2026/01/"}, True),
        ("GetObject", "processed/2026/01/customer-10001/profile.pdf", {"versionId": "v000001"}, True),
        ("DeleteObject", "processed/2026/01/customer-10001/profile.pdf", {"versionId": "v000001"}, False),
        ("DeleteObjects", None, {"delete": {"objects": [{"key": "tmp/session-10001.bin"}, {"key": "tmp/session-10002.bin"}]}}, False),
        ("CreateMultipartUpload", "lake/orders/dt=2026-01-05/part-00001.parquet", {"contentType": "application/octet-stream"}, False),
        ("UploadPart", "lake/orders/dt=2026-01-05/part-00001.parquet", {"partNumber": 1, "uploadId": "upload-0001"}, False),
        ("UploadPartCopy", "lake/orders/dt=2026-01-05/part-00001.parquet", {"partNumber": 2, "uploadId": "upload-0001"}, False),
        ("ListParts", "lake/orders/dt=2026-01-05/part-00001.parquet", {"uploadId": "upload-0001"}, True),
        ("CompleteMultipartUpload", "lake/orders/dt=2026-01-05/part-00001.parquet", {"uploadId": "upload-0001"}, False),
        ("CreateMultipartUpload", "lake/orders/dt=2026-01-05/aborted.parquet", {"contentType": "application/octet-stream"}, False),
        ("AbortMultipartUpload", "lake/orders/dt=2026-01-05/aborted.parquet", {"uploadId": "upload-0002"}, False),
        ("ListMultipartUploads", None, {"prefix": "lake/orders/"}, True),
        ("RestoreObject", "archive/2026/01/customer-10001.tar", {"restore": "Days=1"}, False),
        ("GetBucketCors", None, {}, True),
        ("PutBucketCors", None, {"cors": "rules-present"}, False),
        ("PutObjectRetention", "retention/case-10001.json", {"retentionMode": "GOVERNANCE", "retainUntilDate": "2026-01-06T00:00:00Z"}, False),
        ("GetObjectRetention", "retention/case-10001.json", {}, True),
        ("PutObjectLegalHold", "retention/case-10001.json", {"legalHold": "OFF"}, False),
        ("GetObjectLegalHold", "retention/case-10001.json", {}, True),
        ("GetObjectLockConfiguration", None, {}, True),
        ("PutObjectLockConfiguration", None, {"objectLockConfiguration": "enabled"}, False),
        ("HeadObject", "missing/customer-99999.pdf", {}, True),
        ("GetObject", "encoded/2026/01/customer%2010001/report+final.pdf", {"Range": "bytes=10-20"}, True),
    ]
    events: list[dict[str, Any]] = []
    for index, (event_name, key, params, read_only) in enumerate(specs):
        event_time = base_time + timedelta(minutes=index)
        events.append(_event(bucket, event_name, key, params, read_only, event_time, index))
    truncated = _event(bucket, "GetObject", "logs/2026/01/05/access-0001.json", {}, True, base_time + timedelta(minutes=len(specs)), len(specs))
    truncated.pop("responseElements")
    truncated["requestParameters"] = {"bucketName": bucket}
    events.append(truncated)
    presigned = _event(bucket, "GetObject", "public/2026/01/asset-10001.png", {}, True, base_time + timedelta(minutes=len(specs) + 1), len(specs) + 1)
    presigned["additionalEventData"]["authType"] = "REST-QUERY-STRING"
    presigned["additionalEventData"]["presigned"] = True
    events.append(presigned)
    error_event = _event(bucket, "HeadObject", "uploads/2026/01/customer-40404/profile.pdf", {}, True, base_time + timedelta(minutes=len(specs) + 2), len(specs) + 2)
    error_event["errorCode"] = "NoSuchKey"
    error_event["errorMessage"] = "Not found"
    events.append(error_event)
    for offset, (code, message, event_name, params) in enumerate(
        [
            ("AccessDenied", "Access denied", "GetObject", {}),
            ("InvalidRange", "Invalid range", "GetObject", {"Range": "bytes=999999-1000000"}),
            ("PreconditionFailed", "Precondition failed", "HeadObject", {"If-Match": "\"etag-mismatch\""}),
            ("InvalidRequest", "Invalid request", "PutObject", {"x-amz-request-payer": "requester"}),
        ],
        start=3,
    ):
        err = _event(bucket, event_name, f"errors/2026/01/error-{offset}.json", params, event_name != "PutObject", base_time + timedelta(minutes=len(specs) + offset), len(specs) + offset)
        err["errorCode"] = code
        err["errorMessage"] = message
        events.append(err)
    return events


def _expand_events(seed: list[dict[str, Any]], event_count: int) -> list[dict[str, Any]]:
    if event_count <= len(seed):
        return seed[:event_count]
    events: list[dict[str, Any]] = []
    for index in range(event_count):
        source = json.loads(json.dumps(seed[index % len(seed)]))
        cycle = index // len(seed)
        source["eventTime"] = (datetime.fromisoformat(source["eventTime"].replace("Z", "+00:00")) + timedelta(days=cycle)).isoformat().replace("+00:00", "Z")
        source["eventID"] = f"event-{index:06d}"
        source["requestID"] = f"req-{index:06d}"
        params = source.get("requestParameters") or {}
        if isinstance(params.get("key"), str):
            params["key"] = params["key"].replace("10001", f"{10001 + index:05d}").replace("0001", f"{index % 9999:04d}")
        resources = source.get("resources") or []
        for resource in resources:
            arn = resource.get("ARN")
            if isinstance(arn, str):
                resource["ARN"] = arn.replace("10001", f"{10001 + index:05d}").replace("0001", f"{index % 9999:04d}")
        events.append(source)
    return events


def _event(bucket: str, event_name: str, key: str | None, params: dict[str, Any], read_only: bool, event_time: datetime, index: int) -> dict[str, Any]:
    request_params = {"bucketName": bucket, **params}
    resources = [{"ARN": f"arn:example:s3:::{bucket}"}]
    if key is not None:
        request_params["key"] = key
        resources = [{"ARN": f"arn:example:s3:::{bucket}/{key}"}]
    return {
        "eventVersion": "1.09",
        "eventTime": event_time.isoformat().replace("+00:00", "Z"),
        "eventSource": GENERIC_EVENT_SOURCE,
        "eventName": event_name,
        "region": "us-east-1",
        "sourceIPAddress": f"192.0.2.{(index % 200) + 1}",
        "userAgent": _user_agent(index),
        "requestParameters": request_params,
        "responseElements": {"x-amz-request-id": f"req-{index:06d}"},
        "additionalEventData": _additional_data(event_name, params),
        "readOnly": read_only,
        "resources": resources,
        "recipientAccountId": f"{100000000000 + index:012d}",
        "requestID": f"req-{index:06d}",
        "eventID": f"event-{index:06d}",
    }


def _additional_data(event_name: str, params: dict[str, Any]) -> dict[str, Any]:
    data = {"SignatureVersion": "SigV4"}
    if "x-amz-server-side-encryption" in params or event_name in {"PutObject", "CreateMultipartUpload"}:
        data["SSEApplied"] = params.get("x-amz-server-side-encryption", "AES256")
    if "versionId" in params:
        data["versionIdPresent"] = True
    return data


def _user_agent(index: int) -> str:
    agents = ["app-uploader/3.4", "browser-client/9.1", "batch-ingest/2.0", "retention-worker/1.7", "analytics-loader/5.2"]
    return agents[index % len(agents)]


def _request_hints() -> dict[str, Any]:
    return {
        "presigned": {"observed": True, "methods": ["GET", "PUT"], "max_expiration_seconds": 3600},
        "cors": {
            "origins": ["https://app.example.invalid", "https://partner.example.invalid"],
            "methods": ["GET", "PUT", "HEAD"],
            "request_headers": ["Content-Type", "x-amz-meta-client-id", "x-amz-meta-source-system"],
        },
        "metadata_headers": ["x-amz-meta-client-id", "x-amz-meta-source-system", "x-amz-meta-ingest-id"],
        "object_tags": {"examples": ["environment=test&app=orders&pii=false"]},
        "content_types": ["application/pdf", "image/png", "application/octet-stream", "application/json"],
        "conditional_requests": {"if_none_match": True, "if_match": True},
        "range_gets": {"observed": True},
        "object_lock": {"retention_mode": "GOVERNANCE", "legal_hold": False, "retain_days": 1},
        "expected_error_shapes": {"compare_xml_error_code": True, "compare_http_status": True, "compare_error_message": False},
        "body_classes": ["tiny_text", "small_pdf", "small_png", "parquet_partition", "json_document"],
        "presigned_expiration_buckets": [60, 300, 900, 3600],
        "object_size_distribution": {"0_1KiB": 20, "1KiB_1MiB": 45, "1MiB_128MiB": 30, "128MiB_plus": 5},
        "requester_pays": {"observed": True, "header": "x-amz-request-payer"},
        "pagination": {"continuation_tokens_observed": True, "max_keys_values": [1, 1000]},
        "consistency_expectations": {"read_after_write": True, "list_after_write": True},
    }


def _bucket_config() -> dict[str, Any]:
    return {
        "versioning": {"status": "Enabled"},
        "object_lock": {"enabled": True, "default_retention": {"mode": "GOVERNANCE", "days": 30}},
        "cors": {
            "rules": [
                {
                    "allowed_origins": ["https://app.example.invalid", "https://partner.example.invalid"],
                    "allowed_methods": ["GET", "PUT", "HEAD"],
                    "allowed_headers": ["Content-Type", "x-amz-meta-client-id", "x-amz-meta-source-system"],
                }
            ]
        },
        "lifecycle": {"rules": [{"id": "expire-temp", "prefix": "tmp/", "expiration_days": 30}]},
        "ownership_controls": {"bucket_owner_enforced": True},
        "requester_pays": False,
        "encryption": {"default": "SSE-S3", "customer_provided_keys_observed": False},
        "replication": {"rules": [{"id": "redacted-replication", "status": "Enabled", "prefix": "archive/"}]},
        "event_notifications": {"rules": [{"event": "ObjectCreated", "destination_type": "queue", "prefix": "uploads/"}]},
        "policy_context": _policy_context(),
    }


def _business_context() -> dict[str, Any]:
    return {
        "workload_types": WORKLOAD_TYPES,
        "critical_flows": [
            "Browser users upload documents with CORS and metadata headers.",
            "External partners download files through presigned URLs.",
            "Retention workers apply short synthetic retention in lab buckets.",
            "Data lake ingestion writes multipart partitioned objects.",
            "Support tooling uses version IDs for recovery and audit review.",
        ],
        "business_questions": [
            "Which browser origins and request headers must be supported?",
            "Are presigned URLs used by external users?",
            "Does application logic depend on version IDs?",
            "Which tags and metadata fields are application-required?",
            "Which retention behaviors need lab-bucket validation?",
        ],
    }


def _policy_context() -> dict[str, Any]:
    return {
        "identity_shapes": [
            {"principal_class": "application_role", "session_type": "server_sdk", "operation_families": ["object_read", "object_write", "tagging"]},
            {"principal_class": "browser_user", "session_type": "presigned_url", "operation_families": ["presigned", "cors"]},
            {"principal_class": "batch_role", "session_type": "scheduled_job", "operation_families": ["multipart", "object_list"]},
            {"principal_class": "retention_operator", "session_type": "automation", "operation_families": ["object_lock", "versioning"]},
        ],
        "authorization_shapes": [
            {"effect": "allow", "resource_class": "scratch_prefix", "conditions": ["tls_required"]},
            {"effect": "deny", "resource_class": "non_scratch_prefix", "conditions": ["outside_test_scope"]},
        ],
        "ownership_expectations": {"bucket_owner_enforced": True, "acl_calls_may_be_incidental": False},
    }


def _corpus_calibration() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "local_private_corpus_or_generated_fixture",
        "case_count_bucket": "10_100",
        "family_frequency": {family: "observed" for family in FULL_FAMILIES},
        "note": "Use a private redacted corpus to replace this generated calibration for field decisions.",
    }


def _http_trace(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        params = event.get("requestParameters") or {}
        key = params.get("key") or params.get("prefix") or ""
        method = _http_method(event.get("eventName"))
        rows.append(
            {
                "schema_version": 1,
                "timestamp": event.get("eventTime"),
                "method": method,
                "bucket": "bucket_001",
                "key_shape": _rough_key_shape(str(key)) if key else "",
                "path_template": f"/bucket_001/{_rough_key_shape(str(key))}" if key else "/bucket_001",
                "headers": {
                    "range": "bytes=0-1023" if event.get("eventName") == "GetObject" and index % 3 == 0 else None,
                    "if-match": "\"etag-synthetic\"" if index % 11 == 0 else None,
                    "if-none-match": "*" if index % 13 == 0 else None,
                    "x-amz-meta-client-id": "value_redacted" if method in {"PUT", "POST"} else None,
                    "x-amz-request-payer": "requester" if index % 17 == 0 else None,
                },
                "query_auth": bool((event.get("additionalEventData") or {}).get("presigned")),
                "status_code": 404 if event.get("errorCode") == "NoSuchKey" else 200,
                "error_code": event.get("errorCode"),
                "duration_ms": 20 + (index % 9) * 7,
                "retry_count": index % 3,
                "body_class": _body_class(str(key), event.get("eventName")),
            }
        )
    return rows


def _server_access_log(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        params = event.get("requestParameters") or {}
        key = params.get("key") or params.get("prefix") or ""
        rows.append(
            {
                "schema_version": 1,
                "timestamp": event.get("eventTime"),
                "remote_ip_class": "external_redacted" if index % 5 == 0 else "internal_redacted",
                "requester_shape": _user_agent(index).split("/")[0],
                "operation": event.get("eventName"),
                "key_shape": _rough_key_shape(str(key)) if key else "",
                "status_code": 404 if event.get("errorCode") == "NoSuchKey" else 200,
                "error_code": event.get("errorCode"),
                "bytes_sent_bucket": ["0_1KiB", "1KiB_1MiB", "1MiB_128MiB", "128MiB_plus"][index % 4],
                "object_size_bucket": ["0_1KiB", "1KiB_1MiB", "1MiB_128MiB", "128MiB_plus"][index % 4],
                "total_time_ms": 30 + (index % 10) * 11,
                "turn_around_time_ms": 15 + (index % 10) * 5,
                "header_classes": ["range"] if event.get("eventName") == "GetObject" else ["metadata"] if event.get("eventName") == "PutObject" else [],
            }
        )
    return rows


def _semantic_gap_result(probe: Any) -> ProbeResult:
    result = ProbeResult(probe_id=probe.id, family=probe.family)
    first_step = probe.steps[0] if probe.steps else (probe.setup[0] if probe.setup else None)
    operation = first_step.operation if first_step else probe.family
    status_code = _simulated_status_for_probe(probe)
    result.steps = [ProbeStepResult(operation=operation, status_code=status_code, error_code=None, critical_headers={}, duration_ms=25)]
    mismatch = None
    if probe.family == "presigned":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "200", "403", "PRESIGNED_URL_FAILED", "Target rejected generated presigned URL.")
    elif probe.family == "cors":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "CORS allow headers present", "headers absent", "CORS_PREFLIGHT_MISMATCH", "Target did not return expected CORS allow headers.")
    elif probe.family == "versioning" and probe.required:
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "Status=Enabled", "Status absent", "VERSIONING_TARGET_NOT_ENABLED", "Target bucket versioning behavior was not enabled.")
    elif probe.family == "tagging":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "tag round trip", "missing tag", "TAGGING_ROUNDTRIP_FAILED", "Synthetic object tags did not round trip.")
    elif probe.family == "acl":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "ACL call accepted", "405", "ACL_UNSUPPORTED_OR_DISABLED", "Target rejected or disabled ACL behavior.", severity="REVIEW")
    elif probe.family == "multipart":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "multipart complete succeeds", "minimum part constraint differed", "MULTIPART_COMPLETE_FAILED", "Target multipart completion did not match expected behavior.")
    elif probe.family == "object_lock":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "retention accepted", "unsupported", "OBJECT_LOCK_UNSUPPORTED", "Target Object Lock behavior was not available in the scratch bucket.")
    elif probe.family == "lifecycle":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "time-based lifecycle execution tested", "static review only", "LIFECYCLE_NOT_TESTED", "Lifecycle execution is not time-tested in this replay.", severity="REVIEW")
    elif probe.id == "put_get_head_basic":
        result.steps = [
            ProbeStepResult(operation="PutObject", status_code=200, critical_headers={}),
            ProbeStepResult(operation="HeadObject", status_code=200, critical_headers={"Content-Type": "text/plain"}),
            ProbeStepResult(operation="GetObject", status_code=200, critical_headers={}),
        ]
    elif probe.id == "list_prefix_delimiter":
        result.steps = [ProbeStepResult(operation="ListObjectsV2", status_code=200, critical_headers={})]
    elif probe.id == "copy_synthetic_object":
        mismatch = make_mismatch(probe, "CopyObject", "+".join(probe.evidence_source), "200", "501", "COPY_OBJECT_FAILED", "Target rejected server-side copy behavior.")
    elif probe.family == "conditional_requests":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "conditional request accepted", "412", "CONDITIONAL_REQUEST_MISMATCH", "Target conditional request behavior differed.")
    elif probe.family == "range_gets":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "206 with requested bytes", "200 full body", "RANGE_GET_MISMATCH", "Target did not honor the expected Range request.")
    elif probe.family == "metadata":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "metadata round trip", "metadata missing", "METADATA_ROUNDTRIP_FAILED", "Synthetic object metadata did not round trip.")
    elif probe.family == "encryption_headers":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "encryption header present", "header absent", "ENCRYPTION_HEADER_MISMATCH", "Target encryption response headers differed.", severity="REVIEW")
    elif probe.family == "presigned_expiry":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "expiration boundaries accepted", "boundary failed", "PRESIGNED_EXPIRY_MISMATCH", "Target presigned URL expiration boundary behavior differed.", severity="REVIEW")
    elif probe.family == "list_pagination":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "continuation token present", "token absent", "LIST_PAGINATION_TOKEN_MISSING", "Target did not return expected pagination continuation behavior.", severity="REVIEW")
    elif probe.family == "versioning_delete_marker":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "delete marker present", "delete marker absent", "DELETE_MARKER_BEHAVIOR_MISMATCH", "Target delete marker behavior differed.")
    elif probe.family == "consistency":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "read/list after write visible", "visibility delayed", "CONSISTENCY_MODEL_MISMATCH", "Target immediate read/list visibility differed.", severity="REVIEW")
    elif probe.family == "authz_context":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "authorization context classified", "human review required", "AUTHZ_CONTEXT_REVIEW_REQUIRED", "Authorization and semantic failures require policy-owner review.", severity="REVIEW")
    elif probe.family == "ownership_controls":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "ownership controls compatible", "needs review", "OWNERSHIP_CONTROLS_MISMATCH", "Target ownership controls require review.", severity="REVIEW")
    elif probe.family == "requester_pays":
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "requester pays header accepted", "header rejected", "REQUESTER_PAYS_MISMATCH", "Target requester-pays behavior differed.", severity="REVIEW")
    if mismatch:
        result.mismatches = [mismatch]
        result.steps[0].mismatches = [mismatch]
        result.status = "FAIL" if mismatch.severity == "BLOCKER" else "REVIEW"
        result.severity = mismatch.severity
    return result


def _simulated_status_for_probe(probe: Any) -> int | None:
    return {
        "presigned": 403,
        "cors": 403,
        "acl": 405,
        "multipart": 400,
        "object_lock": 501,
        "lifecycle": None,
    }.get(probe.family, 200)


def _expected_status(expect: dict[str, Any]) -> int | None:
    status = expect.get("status")
    return status if isinstance(status, int) else 200


def _input_coverage(
    cloudtrail_path: str | Path | None,
    request_hints_path: str | Path | None,
    bucket_config_path: str | Path | None,
    *,
    http_trace_path: str | Path | None = None,
    server_access_log_path: str | Path | None = None,
    policy_context_path: str | Path | None = None,
    business_context_path: str | Path | None = None,
    corpus_calibration_path: str | Path | None = None,
) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    families: Counter[str] = Counter()
    event_names: Counter[str] = Counter()
    key_shapes: Counter[str] = Counter()
    feature_evidence: set[str] = set()
    if cloudtrail_path:
        events, warnings = parse_cloudtrail(cloudtrail_path)
        coverage["event_count"] = len(events)
        coverage["parse_warnings"] = warnings
        for event in events:
            event_names[event.eventName or "UNKNOWN"] += 1
            family = FAMILY_BY_EVENT.get(event.eventName or "", "unknown")
            if event.requestParameters and "versionId" in event.requestParameters:
                family = "versioning"
            families[family] += 1
            key = (event.requestParameters or {}).get("key") if event.requestParameters else None
            if isinstance(key, str):
                key_shapes[_rough_key_shape(key)] += 1
            evidence_text = json.dumps({"request": event.requestParameters or {}, "additional": event.additionalEventData or {}}, sort_keys=True).lower()
            if "sse" in evidence_text or "server-side-encryption" in evidence_text:
                feature_evidence.add("encryption_headers")
            if "presigned" in evidence_text or "query-string" in evidence_text:
                feature_evidence.add("presigned")
        coverage["event_names"] = dict(sorted(event_names.items()))
        coverage["operation_families"] = dict(sorted(families.items()))
        coverage["key_shape_count"] = len(key_shapes)
        coverage["has_errors"] = any(bool(event.errorCode) for event in events)
        coverage["error_shape_count"] = len({event.errorCode for event in events if event.errorCode})
        coverage["has_missing_or_truncated_fields"] = any(event.requestParameters is None or event.responseElements is None for event in events)
        coverage["has_multiple_input_formats"] = Path(cloudtrail_path).is_dir() and sum(1 for path in Path(cloudtrail_path).iterdir() if path.is_file()) >= 2
        coverage["feature_evidence"] = sorted(feature_evidence)
        coverage["has_unusual_key_character_set"] = any(
            isinstance((event.requestParameters or {}).get("key"), str)
            and any(token in (event.requestParameters or {}).get("key", "") for token in ("%20", "+", "=", "%2B"))
            for event in events
        )
    if request_hints_path:
        hints = load_request_hints(request_hints_path)
        coverage["request_hint_sections"] = [name for name, value in hints.model_dump(mode="json").items() if value not in ({}, [], None)]
        coverage["has_body_classes"] = bool(hints.body_classes)
        coverage["has_presigned_expiration_distribution"] = bool(hints.presigned_expiration_buckets)
        coverage["has_object_size_distribution"] = bool(hints.object_size_distribution)
        coverage["has_requester_pays_traffic"] = bool(hints.requester_pays)
        coverage["has_pagination_token_distribution"] = bool(hints.pagination)
        coverage["has_consistency_expectations"] = bool(hints.consistency_expectations)
    if bucket_config_path:
        bucket_config = load_bucket_config(bucket_config_path)
        coverage["bucket_config_sections"] = [name for name, value in bucket_config.model_dump(mode="json").items() if value not in ({}, [], None)]
        coverage["has_replication_context"] = bool(bucket_config.replication)
        coverage["has_event_notification_context"] = bool(bucket_config.event_notifications)
        coverage["has_bucket_policy_or_ownership_edge_cases"] = bool(bucket_config.policy_context and bucket_config.ownership_controls)
    if http_trace_path:
        traces = _read_jsonl(http_trace_path)
        coverage["http_trace_count"] = len(traces)
        coverage["has_source_http_transcript"] = len(traces) > 0
        coverage["has_exact_header_coverage"] = any(any(value for value in (row.get("headers") or {}).values()) for row in traces)
        coverage["has_user_identity_context"] = any(row.get("requester_shape") or row.get("query_auth") for row in traces)
        coverage["has_latency_or_retry_distribution"] = any("duration_ms" in row or "retry_count" in row for row in traces)
        coverage["has_presigned_expiration_distribution"] = coverage.get("has_presigned_expiration_distribution", False)
    if server_access_log_path:
        logs = _read_jsonl(server_access_log_path)
        coverage["server_access_log_count"] = len(logs)
        coverage["has_server_access_log_correlation"] = len(logs) > 0
        coverage["has_latency_or_retry_distribution"] = coverage.get("has_latency_or_retry_distribution", False) or any("total_time_ms" in row for row in logs)
        coverage["has_large_multipart_distribution"] = any(row.get("object_size_bucket") == "128MiB_plus" for row in logs)
        coverage["has_exact_header_coverage"] = coverage.get("has_exact_header_coverage", False) or any(row.get("header_classes") for row in logs)
    if policy_context_path:
        policy_context = _load_yaml(policy_context_path)
        coverage["has_iam_or_bucket_policy_context"] = bool(policy_context.get("authorization_shapes"))
        coverage["has_user_identity_context"] = coverage.get("has_user_identity_context", False) or bool(policy_context.get("identity_shapes"))
        coverage["has_bucket_policy_or_ownership_edge_cases"] = coverage.get("has_bucket_policy_or_ownership_edge_cases", False) or bool(policy_context.get("ownership_expectations"))
    if business_context_path:
        business_context = _load_yaml(business_context_path)
        coverage["has_application_confirmation_context"] = bool(business_context.get("business_questions"))
    if corpus_calibration_path:
        corpus_calibration = _load_yaml(corpus_calibration_path)
        coverage["has_real_customer_distribution_support"] = bool(corpus_calibration.get("family_frequency"))
    observed = set(families) | set(coverage.get("feature_evidence", [])) | ({"presigned"} if "presigned" in coverage.get("request_hint_sections", []) else set())
    coverage["family_coverage_percent"] = round(100 * len(observed & set(FULL_FAMILIES)) / len(FULL_FAMILIES), 1)
    return coverage


def _output_coverage(
    profile_path: str | Path | None,
    plan_path: str | Path | None,
    results_path: str | Path | None,
    summary_path: str | Path | None,
    *,
    matrix_path: str | Path | None = None,
    questionnaire_path: str | Path | None = None,
    business_context_path: str | Path | None = None,
) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    profile_families: set[str] = set()
    plan_families: set[str] = set()
    if profile_path:
        profile = UsageProfile(**read_json(profile_path))
        profile_families = {name for name, family in profile.operation_families.items() if family.count > 0}
        coverage["profile_processed_events"] = profile.processed_event_count
        coverage["profile_families"] = sorted(profile_families)
        coverage["observed_features"] = profile.observed_features
        coverage["evidence_quality"] = profile.evidence_quality.model_dump(mode="json")
    if plan_path:
        plan = plan_from_yaml(Path(plan_path).read_text(encoding="utf-8"))
        plan_families = {probe.family for probe in plan.probes}
        coverage["plan_probe_count"] = len(plan.probes)
        coverage["plan_families"] = sorted(plan_families)
        operations = {step.operation for probe in plan.probes for step in [*probe.setup, *probe.steps]}
        coverage["plan_operations"] = sorted(operations)
        coverage["required_probe_count"] = sum(1 for probe in plan.probes if probe.required)
        coverage["unsafe_probe_count"] = sum(1 for probe in plan.probes if probe.requires_allow_deletes or probe.requires_allow_acl_tests or probe.requires_allow_multipart or probe.requires_allow_object_lock_tests)
        coverage["has_conditional_request_probes"] = "ConditionalGetObject" in operations
        coverage["has_range_get_probes"] = "GetObjectRange" in operations
        coverage["has_encryption_header_probes"] = "PutObjectEncryption" in operations
        coverage["has_metadata_header_roundtrip_probes"] = "metadata" in plan_families
        coverage["has_presigned_expiry_boundary_probes"] = "PresignedExpiryBoundary" in operations
        coverage["has_cors_multi_origin_matrix"] = sum(1 for probe in plan.probes if probe.family == "cors") >= 2
        coverage["has_list_pagination_probes"] = "ListObjectsV2Pagination" in operations
        coverage["has_delete_marker_deep_probes"] = "versioning_delete_marker" in plan_families
        coverage["has_lifecycle_validation_plan"] = "LifecycleValidationPlan" in operations
        coverage["has_consistency_model_probes"] = "consistency" in plan_families
        coverage["has_policy_authz_differentiation"] = "authz_context" in plan_families
        coverage["has_ownership_controls_probes"] = "ownership_controls" in plan_families
        coverage["has_requester_pays_probes"] = "requester_pays" in plan_families
    if results_path:
        results = ProbeResults(**read_json(results_path))
        mismatches = collect_mismatches(results)
        coverage["result_status_counts"] = dict(Counter(result.status for result in results.results))
        coverage["result_family_counts"] = dict(Counter(result.family for result in results.results))
        coverage["mismatch_code_counts"] = dict(Counter(mismatch.mismatch_code for mismatch in mismatches))
        coverage["business_blocker_count"] = sum(1 for mismatch in mismatches if mismatch.severity == "BLOCKER")
        coverage["review_count"] = sum(1 for mismatch in mismatches if mismatch.severity == "REVIEW")
        coverage["result_source"] = results.result_source
        coverage["has_results_provenance"] = bool(results.result_source)
        coverage["has_timing_distribution"] = any(step.duration_ms is not None for result in results.results for step in result.steps)
        coverage["has_generic_business_impact"] = any("Observed object-storage behavior may differ" in mismatch.business_impact for mismatch in mismatches)
    if summary_path:
        coverage["summary_status"] = read_json(summary_path).get("compatibility_status")
    if matrix_path:
        matrix = read_json(matrix_path)
        coverage["has_multi_region_or_addressing_matrix"] = matrix.get("target_count", 0) >= 1
    if questionnaire_path:
        questionnaire = _load_yaml(questionnaire_path)
        coverage["has_application_confirmation_required_fields"] = any(bool(item.get("answer_required", True)) for item in questionnaire.get("questions", []))
    if business_context_path:
        business_context = _load_yaml(business_context_path)
        coverage["has_application_confirmation_required_fields"] = coverage.get("has_application_confirmation_required_fields", False) or bool(business_context.get("business_questions"))
    denominator = len(profile_families or plan_families or set(FULL_FAMILIES))
    coverage["plan_family_coverage_percent"] = round(100 * len((profile_families & plan_families) if profile_families else plan_families) / max(denominator, 1), 1)
    return coverage


def _business_findings(results_path: str | Path | None, summary_path: str | Path | None) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if results_path:
        results = ProbeResults(**read_json(results_path))
        for mismatch in collect_mismatches(results):
            if mismatch.severity in {"BLOCKER", "REVIEW"}:
                findings.append(
                    {
                        "severity": mismatch.severity,
                        "code": mismatch.mismatch_code,
                        "business_impact": mismatch.business_impact,
                        "question": mismatch.suggested_human_question,
                    }
                )
    if not findings and summary_path:
        summary = read_json(summary_path)
        for risk in summary.get("top_risks", []):
            findings.append({"severity": risk.get("severity", "REVIEW"), "code": risk.get("code", "UNKNOWN"), "business_impact": risk.get("business_impact", ""), "question": ""})
    return findings[:20]


def _input_gaps(coverage: dict[str, Any]) -> list[GapFinding]:
    gaps: list[GapFinding] = []
    checks = [
        ("has_source_http_transcript", "NO_SOURCE_HTTP_TRANSCRIPT", "Generated data is CloudTrail-style, not a full HTTP request transcript.", "Header-level dependencies may remain hidden.", "Add optional sanitized HTTP trace adapter fixtures."),
        ("has_body_classes", "NO_OBJECT_BODIES", "Object bodies are intentionally absent.", "Content-sensitive behavior and transformations are not validated.", "Keep body-free design but add synthetic body class hints."),
        ("has_iam_or_bucket_policy_context", "NO_IAM_OR_BUCKET_POLICY_CONTEXT", "Access policy and identity context are not represented.", "Authorization failures may be misclassified as endpoint semantic gaps.", "Add offline policy-context hints without source account calls."),
        ("has_server_access_log_correlation", "NO_SERVER_ACCESS_LOG_CORRELATION", "Server access logs are not generated.", "Status/header coverage is weaker than real request logs.", "Add a sanitized access-log fixture generator."),
        ("has_user_identity_context", "NO_USER_IDENTITY_CONTEXT", "Principal, role, and session context are not modeled beyond generic event fields.", "Different auth paths may have different compatibility or policy failures.", "Add redacted identity-shape fields that preserve role class without names."),
        ("has_exact_header_coverage", "NO_EXACT_HEADER_COVERAGE", "Only selected request parameters and hints represent headers.", "Applications depending on subtle header semantics may be missed.", "Add sanitized server access log or HTTP trace adapters."),
        ("has_latency_or_retry_distribution", "NO_LATENCY_OR_RETRY_DISTRIBUTION", "Input data does not include retry counts or latency histograms.", "Operational risk cannot be estimated from generated evidence.", "Add optional informational timing fields while preserving the no-benchmark boundary."),
        ("has_real_customer_distribution_support", "NO_REAL_CUSTOMER_DISTRIBUTION", "Generated volumes are deterministic and representative, not sampled from a real customer corpus.", "Frequency estimates should not drive staffing or pricing decisions.", "Compare against private redacted case-bundle corpora."),
        ("has_pagination_token_distribution", "NO_PAGINATION_TOKEN_DISTRIBUTION", "List pagination and continuation-token patterns are not varied deeply.", "Large prefix listing behavior may be under-tested.", "Generate list events with continuation token and truncated result shapes."),
        ("has_unusual_key_character_set", "NO_UNUSUAL_KEY_CHARACTER_SET", "Generated keys avoid spaces, unicode, and reserved URL characters.", "Encoding-sensitive clients may fail undetected.", "Add redacted key-shape classes for escaped and non-ASCII key segments."),
        ("has_presigned_expiration_distribution", "NO_PRESIGNED_EXPIRATION_DISTRIBUTION", "Presigned hints include a max expiration but not a realistic distribution.", "Long-lived or short-lived URL behavior may be under-tested.", "Add expiration buckets to request hints and generated probe variants."),
        ("has_event_notification_context", "NO_EVENT_NOTIFICATION_CONTEXT", "Notifications and downstream consumers are not represented.", "Cutover risks around event delivery are outside the current evidence model.", "Add optional offline event-notification config importers."),
        ("has_replication_context", "NO_REPLICATION_CONTEXT", "Replication configuration and replication status headers are not generated.", "Replication-dependent workloads require separate validation.", "Add offline replication config context and static review codes."),
        ("has_requester_pays_traffic", "NO_REQUESTER_PAYS_TRAFFIC", "Requester-pays behavior is static config only.", "Clients that rely on payer headers may fail.", "Add request-hint and probe support for payer headers."),
        ("has_large_multipart_distribution", "NO_LARGE_MULTIPART_DISTRIBUTION", "Multipart events are generated without realistic object-size histograms.", "Part-size and memory behavior may be understated.", "Add size-bucket hints without object data."),
        ("has_bucket_policy_or_ownership_edge_cases", "NO_BUCKET_POLICY_OR_OWNERSHIP_EDGE_CASES", "Ownership controls are static context but object ownership and policy edge cases are not varied.", "ACL and ownership remediation may be under-scoped.", "Add offline ownership and policy-shape fixtures."),
    ]
    for key, code, description, impact, action in checks:
        if not coverage.get(key):
            gaps.append(_gap("input", "REVIEW", code, description, impact, action))
    if int(coverage.get("error_shape_count", 0)) < 4:
        gaps.append(_gap("input", "REVIEW", "LIMITED_ERROR_SHAPE_VARIETY", "Only a small number of source error cases are generated.", "Applications sensitive to specific errors may need more review.", "Add more expected-error fixtures for forbidden, range, precondition, and invalid request cases."))
    observed_families = set(coverage.get("operation_families", {})) | set(coverage.get("feature_evidence", []))
    for family in set(FULL_FAMILIES) - observed_families - ({"presigned"} if "presigned" in coverage.get("request_hint_sections", []) else set()):
        gaps.append(_gap("input", "REVIEW", f"MISSING_{family.upper()}_EVIDENCE", f"No generated source evidence for {family}.", "Probe coverage for that behavior may be absent.", "Add source events, request hints, or bucket config for this family."))
    return gaps


def _output_gaps(coverage: dict[str, Any], results_path: str | Path | None) -> list[GapFinding]:
    gaps: list[GapFinding] = []
    checks = [
        ("has_results_provenance", "SIMULATED_RESULTS_NOT_LIVE_ENDPOINT", "Generated output lacks explicit result provenance.", "It may be unclear whether output validates reporting or a live endpoint.", "Store result_source in probe results."),
        ("has_conditional_request_probes", "NO_CONDITIONAL_REQUEST_PROBES", "Request hints can mark conditional requests but the probe plan does not yet generate If-Match or If-None-Match probes.", "Optimistic concurrency or cache validation flows may fail undetected.", "Implement conditional request probes."),
        ("has_range_get_probes", "NO_RANGE_GET_PROBES", "Range GET hints are observed but no dedicated range probe is generated.", "Media, resume, and partial-read clients may fail after cutover.", "Implement Range header GET probes."),
        ("has_encryption_header_probes", "NO_ENCRYPTION_HEADER_PROBES", "Encryption indicators are profiled but not deeply probed.", "Workloads depending on encryption headers or customer-managed key semantics need separate review.", "Add synthetic SSE header probes using safe lab-only inputs."),
        ("has_metadata_header_roundtrip_probes", "NO_METADATA_HEADER_ROUNDTRIP_PROBES", "Request hints can list metadata headers but only minimal synthetic metadata is checked.", "Applications reading metadata after upload may fail or misroute objects.", "Add metadata-header-specific round-trip probes."),
        ("has_presigned_expiry_boundary_probes", "NO_PRESIGNED_EXPIRY_BOUNDARY_PROBES", "Presigned probes do not validate expiration boundary behavior.", "External links may fail too early or remain valid longer than expected.", "Add short-expiration and max-expiration probe variants."),
        ("has_cors_multi_origin_matrix", "NO_CORS_MULTI_ORIGIN_MATRIX", "CORS probe generation chooses one representative origin and method.", "Secondary browser origins or methods may fail after cutover.", "Generate probes for each hinted origin/method/header group within probe limits."),
        ("has_list_pagination_probes", "NO_LIST_PAGINATION_PROBES", "ListObjectsV2 probes do not force continuation-token behavior.", "Large listings may fail even if small prefix checks pass.", "Add bounded pagination probes with synthetic keys."),
        ("has_delete_marker_deep_probes", "NO_DELETE_MARKER_DEEP_PROBES", "Versioning probes do not deeply compare delete marker behavior.", "Recovery and audit workflows can break around deleted versioned keys.", "Add delete-marker and version-specific read probes."),
        ("has_lifecycle_validation_plan", "LIFECYCLE_STATIC_ONLY", "Lifecycle remains static review only.", "Expiration or transition behavior can surprise operations after cutover.", "Generate lifecycle validation plans without waiting days."),
        ("has_consistency_model_probes", "NO_CONSISTENCY_MODEL_PROBES", "Read-after-write and list consistency are only lightly implied by basic probes.", "Application assumptions about immediate visibility may fail.", "Add repeated read/list consistency probes with bounded timing notes."),
        ("has_policy_authz_differentiation", "NO_POLICY_AUTHZ_DIFFERENTIATION", "The report cannot distinguish semantic unsupported behavior from target authorization policy denial.", "Teams may chase wrong remediation owners.", "Add error-shape and policy-context annotations."),
        ("has_ownership_controls_probes", "NO_OWNERSHIP_CONTROLS_PROBES", "Ownership controls are reported but not probed.", "ACL-disabled or bucket-owner-enforced targets may require app or policy changes.", "Add safe ownership-control static checks and ACL expectation mapping."),
        ("has_requester_pays_probes", "NO_REQUESTER_PAYS_PROBES", "Requester-pays context is not probed.", "Clients requiring payer headers may fail.", "Add optional payer-header probes only when hints require them."),
        ("has_timing_distribution", "NO_TIMING_DISTRIBUTION", "Probe results do not include timing distributions.", "Operational planning cannot use the output as performance evidence.", "Keep benchmark boundary, but include informational latency fields."),
        ("has_multi_region_or_addressing_matrix", "NO_MULTI_REGION_OR_ADDRESSING_MATRIX", "One endpoint/region/addressing style is represented per result file.", "Addressing or region behavior differences may be missed.", "Run matrix comparisons across addressing styles and regions."),
        ("has_application_confirmation_required_fields", "NO_APPLICATION_CONFIRMATION_REQUIRED_FIELDS", "App-owner answers are generated as questions but not enforced as required inputs.", "Important business criticality can remain unknown.", "Add questionnaire answer validation and policy gates."),
    ]
    for key, code, description, impact, action in checks:
        if not coverage.get(key):
            gaps.append(_gap("output", "REVIEW", code, description, impact, action))
    if coverage.get("has_generic_business_impact"):
        gaps.append(_gap("output", "REVIEW", "GENERIC_BUSINESS_IMPACT_FOR_UNKNOWN_CODES", "Some mismatch codes fall back to generic impact text.", "Reports can be less persuasive for business owners.", "Require business-impact dictionary entries with each new mismatch code."))
    plan_families = set(coverage.get("plan_families", []))
    for family in set(coverage.get("profile_families", [])) - plan_families:
        gaps.append(_gap("output", "REVIEW", f"NO_{family.upper()}_PROBE", f"Observed {family} behavior has no generated probe.", "Observed behavior may be unsupported on the target without detection.", "Add or enable a safe synthetic probe for this family."))
    if results_path:
        results = ProbeResults(**read_json(results_path))
        skipped_required = [result.probe_id for result in results.results if result.status == "SKIP" and result.severity in {"BLOCKER", "REVIEW"}]
        if skipped_required:
            gaps.append(_gap("output", "REVIEW", "REQUIRED_PROBES_SKIPPED", f"Required or review-level probes were skipped: {', '.join(skipped_required)}.", "Human review is needed before treating output as a compatibility preflight pass.", "Run with explicit allow flags in a scratch bucket where safe."))
    return gaps


def _rough_key_shape(key: str) -> str:
    parts = []
    for segment in key.split("/"):
        if segment.startswith("dt="):
            parts.append("dt={date}")
        elif any(ch.isdigit() for ch in segment):
            ext = "." + segment.rsplit(".", 1)[1] if "." in segment else ""
            parts.append("{id}" + ext)
        else:
            parts.append(segment)
    return "/".join(parts)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            loaded = json.loads(stripped)
            if isinstance(loaded, dict):
                rows.append(loaded)
    return rows


def _load_yaml(path: str | Path) -> dict[str, Any]:
    loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def _http_method(event_name: str | None) -> str:
    if not event_name:
        return "GET"
    if event_name.startswith(("Get", "Head", "List")):
        return "HEAD" if event_name.startswith("Head") else "GET"
    if event_name.startswith("Delete"):
        return "DELETE"
    if event_name.startswith(("Put", "Create", "Upload", "Complete", "Abort", "Restore", "Copy")):
        return "PUT"
    return "POST"


def _body_class(key: str, event_name: str | None) -> str:
    if event_name in {"ListObjectsV2", "HeadObject", "GetBucketVersioning"}:
        return "none"
    if key.endswith(".pdf"):
        return "small_pdf"
    if key.endswith(".png"):
        return "small_png"
    if key.endswith(".parquet"):
        return "parquet_partition"
    if key.endswith(".json"):
        return "json_document"
    if key.endswith(".tar"):
        return "archive_bundle"
    return "tiny_text"


def _gap(area: str, severity: str, code: str, description: str, business_impact: str, suggested_action: str) -> GapFinding:
    return GapFinding(area=area, severity=severity, code=code, description=description, business_impact=business_impact, suggested_action=suggested_action)


def _gap_lines(gaps: list[GapFinding]) -> list[str]:
    if not gaps:
        return ["- No gaps identified."]
    return [f"- [{gap.severity}] {gap.code}: {gap.description} Impact: {gap.business_impact} Action: {gap.suggested_action}" for gap in gaps]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
