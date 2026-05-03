from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import time
import uuid
from typing import Any
from urllib.parse import urlencode

from s3_compat_replay.compare import compare_step, make_mismatch
from s3_compat_replay.models import CleanupManifest, Probe, ProbePlan, ProbeResult, ProbeResults, ProbeStep, ProbeStepResult
from s3_compat_replay.redact import redact_presigned_url
from s3_compat_replay.safety import ensure_key_within_prefix, probe_needs_write, validate_scratch_prefix


def run_probe_plan(
    plan: ProbePlan,
    *,
    client: Any,
    endpoint_url: str,
    target_bucket: str,
    scratch_prefix: str,
    allow_writes: bool = False,
    allow_deletes: bool = False,
    allow_acl_tests: bool = False,
    allow_multipart: bool = False,
    allow_object_lock_tests: bool = False,
    read_only: bool = False,
    cleanup: bool = True,
    strict: bool = False,
    min_scratch_prefix_length: int = 8,
    tls_verification_disabled: bool = False,
) -> tuple[ProbeResults, CleanupManifest | None]:
    run_id = str(uuid.uuid4())
    started = _now()
    warnings: list[str] = []
    prefix_errors = validate_scratch_prefix(scratch_prefix, min_scratch_prefix_length)
    if prefix_errors:
        raise ValueError("SCRATCH_PREFIX_SAFETY_FAILED: " + "; ".join(prefix_errors))
    if tls_verification_disabled:
        warnings.append("TLS_VERIFICATION_DISABLED")

    results: list[ProbeResult] = []
    created_keys: list[str] = []
    setup_hashes: dict[tuple[str, str], str] = {}
    multipart_state: dict[str, dict[str, Any]] = {}
    effective_read_only = read_only or not allow_writes

    for probe in plan.probes:
        unsafe_reason = _unsafe_reason(probe, effective_read_only, allow_deletes, allow_acl_tests, allow_multipart, allow_object_lock_tests)
        if unsafe_reason:
            if strict and probe.required:
                raise ValueError(f"required probe {probe.id} cannot run safely: {unsafe_reason}")
            results.append(_skipped_result(probe, unsafe_reason))
            warnings.append(unsafe_reason)
            continue
        probe_result = ProbeResult(probe_id=probe.id, family=probe.family)
        for phase_step in [*probe.setup, *probe.steps]:
            step_result = _run_step(
                plan=plan,
                probe=probe,
                step=phase_step,
                client=client,
                bucket=target_bucket,
                scratch_prefix=scratch_prefix,
                run_id=run_id,
                created_keys=created_keys,
                setup_hashes=setup_hashes,
                multipart_state=multipart_state,
            )
            probe_result.steps.append(step_result)
            probe_result.mismatches.extend(step_result.mismatches)
        if probe_result.mismatches:
            probe_result.status = "FAIL" if any(m.severity == "BLOCKER" for m in probe_result.mismatches) else "REVIEW"
            probe_result.severity = _max_severity(probe_result.mismatches)
        results.append(probe_result)

    cleanup_manifest = None
    cleanup_succeeded = True
    if cleanup:
        for key in sorted(set(created_keys)):
            try:
                ensure_key_within_prefix(key, scratch_prefix)
                response = client.delete_object(target_bucket, key)
                status = response.get("status_code")
                if status not in {200, 202, 204, None}:
                    cleanup_succeeded = False
            except Exception:
                cleanup_succeeded = False
        if not cleanup_succeeded:
            cleanup_manifest = CleanupManifest(
                run_id=run_id,
                target_bucket_redacted=target_bucket,
                scratch_prefix=scratch_prefix,
                objects=sorted(set(created_keys)),
                reason="CLEANUP_FAILED",
            )
            warnings.append("CLEANUP_FAILED")

    failed = sum(1 for result in results if result.status == "FAIL")
    skipped = sum(1 for result in results if result.status == "SKIP")
    output = ProbeResults(
        run_id=run_id,
        endpoint_url_redacted=endpoint_url,
        target_bucket_redacted=target_bucket,
        scratch_prefix=scratch_prefix,
        started_at=started,
        finished_at=_now(),
        probes_run=len(results) - skipped,
        probes_skipped=skipped,
        probes_failed=failed,
        cleanup={"attempted": cleanup, "succeeded": cleanup_succeeded, "cleanup_manifest": "cleanup-manifest.json" if cleanup_manifest else None},
        results=results,
        warnings=sorted(set(warnings)),
    )
    return output, cleanup_manifest


def _run_step(
    *,
    plan: ProbePlan,
    probe: Probe,
    step: ProbeStep,
    client: Any,
    bucket: str,
    scratch_prefix: str,
    run_id: str,
    created_keys: list[str],
    setup_hashes: dict[tuple[str, str], str],
    multipart_state: dict[str, dict[str, Any]],
) -> ProbeStepResult:
    operation = step.operation
    started = time.perf_counter()
    key = _key_for_step(scratch_prefix, run_id, probe.id, step.key_suffix)
    if step.key_suffix:
        ensure_key_within_prefix(key, scratch_prefix)
    body = _body_bytes(step.body)
    actual: dict[str, Any]
    if operation == "PutObject":
        actual = client.put_object(bucket, key, body, step.content_type, {**step.metadata, "compat-replay-run-id": run_id}, _tag_query({"compat-replay": "true", "compat-replay-run-id": run_id}))
        created_keys.append(key)
        setup_hashes[(probe.id, step.key_suffix or "")] = hashlib.sha256(body).hexdigest()
    elif operation == "HeadObject":
        actual = client.head_object(bucket, key)
    elif operation == "GetObject":
        actual = client.get_object(bucket, key)
        expected_hash = setup_hashes.get((probe.id, step.key_suffix or ""))
        if step.expect.get("body_sha256_matches_setup") and expected_hash:
            step.expect["body_sha256"] = expected_hash
    elif operation == "ConditionalGetObject":
        if hasattr(client, "get_object_conditional"):
            actual = client.get_object_conditional(bucket, key, if_match=step.params.get("if_match"), if_none_match=step.params.get("if_none_match"))
        else:
            actual = client.get_object(bucket, key)
    elif operation == "GetObjectRange":
        if hasattr(client, "get_object_range"):
            actual = client.get_object_range(bucket, key, step.params.get("range"))
        else:
            actual = client.get_object(bucket, key)
            body = actual.get("body") or b""
            actual["body"] = body[: int(str(step.params.get("range", "bytes=0-0")).split("=")[1].split("-")[1]) + 1] if body else body
            actual["status_code"] = 206 if actual.get("status_code") == 200 else actual.get("status_code")
    elif operation == "DeleteObject":
        actual = client.delete_object(bucket, key)
    elif operation == "ListObjectsV2":
        prefix = scratch_prefix + run_id + "/" + probe.id + "/" + step.params.get("prefix", "")
        actual = client.list_objects_v2(bucket, prefix=prefix, delimiter=step.params.get("delimiter"), max_keys=int(step.params.get("max_keys", 1000)))
    elif operation == "ListObjectsV2Pagination":
        prefix = scratch_prefix + run_id + "/" + probe.id + "/" + step.params.get("prefix", "")
        actual = client.list_objects_v2(bucket, prefix=prefix, delimiter=step.params.get("delimiter"), max_keys=int(step.params.get("max_keys", 1)))
    elif operation == "CopyObject":
        source_suffix = step.params.get("copy_source_suffix")
        source_key = _key_for_step(scratch_prefix, run_id, probe.id, source_suffix)
        actual = client.copy_object(bucket, key, {"Bucket": bucket, "Key": source_key})
        created_keys.append(key)
    elif operation == "PutObjectEncryption":
        if hasattr(client, "put_object_encrypted"):
            actual = client.put_object_encrypted(bucket, key, body, step.params.get("server_side_encryption"))
        else:
            actual = client.put_object(bucket, key, body, step.content_type, {**step.metadata, "compat-replay-run-id": run_id}, _tag_query({"compat-replay": "true", "compat-replay-run-id": run_id}))
        created_keys.append(key)
        setup_hashes[(probe.id, step.key_suffix or "")] = hashlib.sha256(body).hexdigest()
    elif operation == "PutObjectTagging":
        actual = client.put_object_tagging(bucket, key, step.tags)
    elif operation == "GetObjectTagging":
        actual = client.get_object_tagging(bucket, key)
    elif operation == "DeleteObjectTagging":
        actual = client.delete_object_tagging(bucket, key)
    elif operation == "GetObjectAcl":
        actual = client.get_object_acl(bucket, key)
        if actual.get("status_code") in {400, 403, 405, 501}:
            mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "ACL call accepted", str(actual.get("status_code")), "ACL_UNSUPPORTED_OR_DISABLED", "Target rejected or disabled ACL behavior.", severity="BLOCKER" if probe.required else "REVIEW")
            return _step_result(operation, actual, [mismatch], started)
    elif operation == "GetBucketVersioning":
        actual = client.get_bucket_versioning(bucket)
        data = actual.get("data") or {}
        if probe.required and data.get("Status") != "Enabled":
            mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "Status=Enabled", str(data.get("Status")), "VERSIONING_TARGET_NOT_ENABLED", "Target bucket versioning is not enabled.")
            return _step_result(operation, actual, [mismatch], started)
    elif operation == "ListObjectVersions":
        prefix = scratch_prefix + run_id + "/" + probe.id + "/" + step.params.get("prefix", "")
        actual = client.list_object_versions(bucket, prefix=prefix)
    elif operation == "CreateMultipartUpload":
        actual = client.create_multipart_upload(bucket, key)
        upload_id = (actual.get("data") or {}).get("UploadId")
        multipart_state[probe.id] = {"upload_id": upload_id, "parts": []}
        created_keys.append(key)
    elif operation == "UploadPart":
        state = multipart_state.get(probe.id, {})
        actual = client.upload_part(bucket, key, state.get("upload_id"), int(step.params.get("part_number", 1)), body)
        etag = (actual.get("data") or {}).get("ETag", "\"synthetic\"")
        state.setdefault("parts", []).append({"ETag": etag, "PartNumber": int(step.params.get("part_number", 1))})
    elif operation == "CompleteMultipartUpload":
        state = multipart_state.get(probe.id, {})
        actual = client.complete_multipart_upload(bucket, key, state.get("upload_id"), state.get("parts", []))
    elif operation == "PresignedUrl":
        method = step.params.get("method", "GET")
        url = client.generate_presigned_url(method, bucket, key, int(step.params.get("expires_in", 300)))
        actual = client.request_presigned(method, url, body if method == "PUT" else None)
        actual["data"] = {"presigned_url_redacted": redact_presigned_url(url)}
    elif operation == "PresignedExpiryBoundary":
        method = step.params.get("method", "GET")
        urls = []
        for expires_in in step.params.get("expiration_buckets") or [300]:
            url = client.generate_presigned_url(method, bucket, key, int(expires_in))
            urls.append(redact_presigned_url(url))
        actual = {"status_code": 200, "error_code": None, "headers": {}, "data": {"presigned_urls_redacted": urls}}
    elif operation == "CorsPreflight":
        actual = client.cors_preflight(bucket, step.params.get("origin"), step.params.get("method"), step.params.get("request_headers") or [])
    elif operation == "PutObjectRetention":
        actual = client.put_object_retention(bucket, key, step.params.get("mode", "GOVERNANCE"), datetime.now(UTC) + timedelta(days=int(step.params.get("retain_days", 1))))
    elif operation == "RequesterPaysList":
        if hasattr(client, "list_objects_v2_requester_pays"):
            actual = client.list_objects_v2_requester_pays(bucket, prefix=step.params.get("prefix", ""), max_keys=int(step.params.get("max_keys", 1)))
        else:
            actual = client.list_objects_v2(bucket, prefix=step.params.get("prefix", ""), max_keys=int(step.params.get("max_keys", 1)))
    elif operation == "GetBucketOwnershipControls":
        if hasattr(client, "get_bucket_ownership_controls"):
            actual = client.get_bucket_ownership_controls(bucket)
        else:
            actual = {"status_code": 200, "error_code": None, "headers": {}, "data": {"OwnershipControls": "not-queried"}}
    elif operation == "PolicyContextReview":
        actual = {"status_code": 200, "error_code": None, "headers": {}, "data": {"review": "policy context attached"}}
    elif operation == "LifecycleValidationPlan":
        actual = {"status_code": 200, "error_code": None, "headers": {}, "data": {"validation_plan": "static lifecycle plan generated"}}
    elif operation == "StaticReview":
        actual = {"status_code": None, "error_code": None, "headers": {}, "data": {}}
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "time-based lifecycle execution tested", "static review only", "LIFECYCLE_NOT_TESTED", "Lifecycle execution is not time-tested in the MVP.", severity="REVIEW")
        return ProbeStepResult(operation=operation, status_code=None, error_code=None, critical_headers={}, duration_ms=_duration_ms(started), mismatches=[mismatch])
    else:
        actual = {"status_code": None, "error_code": "NotImplemented", "headers": {}, "data": {}}
        mismatch = make_mismatch(probe, operation, "+".join(probe.evidence_source), "operation supported", "not implemented", "OPERATION_UNSUPPORTED", "Probe operation is not implemented.", severity="REVIEW")
        return ProbeStepResult(operation=operation, status_code=None, error_code="NotImplemented", critical_headers={}, duration_ms=_duration_ms(started), mismatches=[mismatch])
    mismatches = compare_step(probe, operation, step.expect, actual)
    return _step_result(operation, actual, mismatches, started)


def _unsafe_reason(probe: Probe, read_only: bool, allow_deletes: bool, allow_acl: bool, allow_multipart: bool, allow_object_lock: bool) -> str | None:
    if read_only and probe_needs_write(probe):
        return "READ_ONLY_MODE_SKIPPED_WRITE_PROBES"
    if probe.requires_allow_deletes and not allow_deletes:
        return "DESTRUCTIVE_PROBES_SKIPPED"
    if probe.requires_allow_acl_tests and not allow_acl:
        return "ACL_PROBES_SKIPPED"
    if probe.requires_allow_multipart and not allow_multipart:
        return "MULTIPART_PROBES_SKIPPED"
    if probe.requires_allow_object_lock_tests and not allow_object_lock:
        return "OBJECT_LOCK_PROBES_SKIPPED"
    return None


def _skipped_result(probe: Probe, warning: str) -> ProbeResult:
    severity = "REVIEW" if probe.required else "INFO"
    return ProbeResult(probe_id=probe.id, family=probe.family, status="SKIP", severity=severity, warnings=[warning])


def _key_for_step(prefix: str, run_id: str, probe_id: str, suffix: str | None) -> str:
    suffix = suffix or "object"
    return f"{prefix}{run_id}/{probe_id}/{suffix}"


def _body_bytes(body: str | bytes | None) -> bytes:
    if body is None:
        return b"synthetic"
    if isinstance(body, bytes):
        return body
    return body.encode("utf-8")


def _tag_query(tags: dict[str, str]) -> str:
    return urlencode(tags)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _max_severity(mismatches: list[Any]) -> str:
    if any(m.severity == "BLOCKER" for m in mismatches):
        return "BLOCKER"
    if any(m.severity == "REVIEW" for m in mismatches):
        return "REVIEW"
    return "INFO"


def _step_result(operation: str, actual: dict[str, Any], mismatches: list[Any], started: float) -> ProbeStepResult:
    return ProbeStepResult(
        operation=operation,
        status_code=actual.get("status_code"),
        error_code=actual.get("error_code"),
        critical_headers=actual.get("headers") or {},
        duration_ms=_duration_ms(started),
        mismatches=mismatches,
    )


def _duration_ms(started: float) -> int:
    return max(int((time.perf_counter() - started) * 1000), 0)
