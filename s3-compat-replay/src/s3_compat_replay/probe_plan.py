from __future__ import annotations

import yaml

from .models import BucketConfig, KeyShape, Probe, ProbePlan, ProbeStep, RequestHints, UsageProfile


def build_probe_plan(
    profile: UsageProfile,
    request_hints: RequestHints | None = None,
    bucket_config: BucketConfig | None = None,
    max_probes: int = 100,
    scratch_prefix: str = "compat-replay/",
) -> ProbePlan:
    request_hints = request_hints or RequestHints()
    bucket_config = bucket_config or BucketConfig()
    probes: list[Probe] = []
    families = set(profile.operation_families)
    features = set(profile.observed_features)
    representative_shape = profile.key_shapes[0] if profile.key_shapes else KeyShape(prefix_template="{segment}/{id}.txt", extension=".txt", slash_depth=1)

    if {"object_read", "object_write", "versioning"} & families:
        probes.append(_basic_put_head_get(representative_shape))
    if "object_read" in families:
        probes.append(_missing_head())
    if "object_list" in families:
        probes.append(_list_prefix_delimiter())
    if "object_delete" in families:
        probes.append(_delete_object())
    if _event_observed(profile, "CopyObject"):
        probes.append(_copy_object())
    if "tagging" in families or "OBJECT_TAGGING" in features:
        probes.append(_tagging())
    if "acl" in families or "ACL" in features:
        probes.append(_acl(required="acl" in families))
    if "versioning" in families or "VERSIONING" in features or bucket_config.versioning:
        probes.append(_versioning(required="versioning" in families or "VERSION_ID" in features))
    if "multipart" in families or "MULTIPART" in features:
        probes.append(_multipart())
    if request_hints.presigned.get("observed") or "PRESIGNED_OBSERVED" in features:
        probes.append(_presigned(request_hints))
    if request_hints.cors or bucket_config.cors or "CORS" in features:
        probes.extend(_cors_probes(request_hints, bucket_config, required=bool(request_hints.cors or bucket_config.cors)))
    if request_hints.conditional_requests or "CONDITIONAL_REQUESTS" in features:
        probes.append(_conditional_requests())
    if request_hints.range_gets.get("observed") or "RANGE_GETS" in features:
        probes.append(_range_get())
    if request_hints.metadata_headers or "METADATA_HEADERS" in features:
        probes.append(_metadata_roundtrip(request_hints))
    if "ENCRYPTION_HEADERS" in features or bucket_config.encryption:
        probes.append(_encryption_headers())
    if request_hints.object_lock or bucket_config.object_lock or "OBJECT_LOCK" in features:
        probes.append(_object_lock(required="OBJECT_LOCK" in features))
    if request_hints.presigned_expiration_buckets:
        probes.append(_presigned_expiry(request_hints))
    if request_hints.pagination or "object_list" in families:
        probes.append(_list_pagination())
    if "versioning" in families or "VERSION_ID" in features:
        probes.append(_versioning_delete_marker())
    if request_hints.consistency_expectations:
        probes.append(_consistency_probe())
    if bucket_config.policy_context:
        probes.append(_authz_context_review())
    if bucket_config.ownership_controls:
        probes.append(_ownership_controls())
    if request_hints.requester_pays or bucket_config.requester_pays is not None:
        probes.append(_requester_pays())
    if bucket_config.lifecycle:
        probes.append(_lifecycle_static())

    deduped: list[Probe] = []
    seen: set[str] = set()
    for probe in probes:
        if probe.id not in seen:
            seen.add(probe.id)
            deduped.append(probe)
    deduped = deduped[:max_probes]
    warnings = []
    if not deduped:
        warnings.append("NO_PROBES_GENERATED")
    return ProbePlan(
        source_bucket=profile.source_bucket,
        generated_at=profile.time_range.last_event_time or "1970-01-01T00:00:00Z",
        scratch_prefix=scratch_prefix,
        safety={
            "uses_synthetic_objects_only": True,
            "destructive_tests_require_allow_deletes": True,
            "object_lock_tests_require_explicit_enable": True,
        },
        probes=deduped,
        warnings=warnings,
    )


def plan_to_yaml(plan: ProbePlan) -> str:
    return yaml.safe_dump(plan.model_dump(mode="json"), sort_keys=False)


def plan_from_yaml(text: str) -> ProbePlan:
    loaded = yaml.safe_load(text) or {}
    return ProbePlan(**loaded)


def _event_observed(profile: UsageProfile, event_name: str) -> bool:
    return any(event_name in family.event_names for family in profile.operation_families.values())


def _basic_put_head_get(shape: KeyShape) -> Probe:
    return Probe(
        id="put_get_head_basic",
        family="object_read",
        required=True,
        evidence_source=["CLOUDTRAIL"],
        synthetic_key_shape=shape,
        requires_allow_writes=True,
        setup=[
            ProbeStep(
                operation="PutObject",
                key_suffix="basic/object.txt",
                body="synthetic",
                content_type="text/plain",
                metadata={"compat-replay": "true"},
                expect={"status": 200},
            )
        ],
        steps=[
            ProbeStep(operation="HeadObject", key_suffix="basic/object.txt", expect={"status": 200, "headers": {"Content-Type": "text/plain"}}),
            ProbeStep(operation="GetObject", key_suffix="basic/object.txt", expect={"status": 200, "body_sha256_matches_setup": True}),
        ],
    )


def _missing_head() -> Probe:
    return Probe(
        id="head_missing_object",
        family="object_read",
        required=True,
        evidence_source=["CLOUDTRAIL"],
        steps=[ProbeStep(operation="HeadObject", key_suffix="missing/does-not-exist.txt", expect={"status": 404, "error_code": "NoSuchKey"})],
    )


def _list_prefix_delimiter() -> Probe:
    return Probe(
        id="list_prefix_delimiter",
        family="object_list",
        required=True,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        setup=[
            ProbeStep(operation="PutObject", key_suffix="list/a/one.txt", body="1", expect={"status": 200}),
            ProbeStep(operation="PutObject", key_suffix="list/a/two.txt", body="2", expect={"status": 200}),
        ],
        steps=[
            ProbeStep(operation="ListObjectsV2", params={"prefix": "list/a/", "delimiter": "/", "max_keys": 1000}, expect={"status": 200})
        ],
    )


def _delete_object() -> Probe:
    return Probe(
        id="delete_synthetic_object",
        family="object_delete",
        required=True,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        requires_allow_deletes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="delete/object.txt", body="delete-me", expect={"status": 200})],
        steps=[ProbeStep(operation="DeleteObject", key_suffix="delete/object.txt", expect={"status": 204})],
    )


def _copy_object() -> Probe:
    return Probe(
        id="copy_synthetic_object",
        family="object_write",
        required=True,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="copy/source.txt", body="copy-source", expect={"status": 200})],
        steps=[ProbeStep(operation="CopyObject", key_suffix="copy/dest.txt", params={"copy_source_suffix": "copy/source.txt"}, expect={"status": 200})],
    )


def _tagging() -> Probe:
    return Probe(
        id="tagging_roundtrip",
        family="tagging",
        required=True,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="tagging/object.txt", body="tagged", expect={"status": 200})],
        steps=[
            ProbeStep(operation="PutObjectTagging", key_suffix="tagging/object.txt", tags={"environment": "test", "compat-replay": "true"}, expect={"status": 200}),
            ProbeStep(operation="GetObjectTagging", key_suffix="tagging/object.txt", expect={"status": 200, "tags": {"environment": "test", "compat-replay": "true"}}),
            ProbeStep(operation="DeleteObjectTagging", key_suffix="tagging/object.txt", expect={"status": 204}),
        ],
    )


def _acl(required: bool) -> Probe:
    return Probe(
        id="acl_get_object",
        family="acl",
        required=required,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        requires_allow_acl_tests=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="acl/object.txt", body="acl", expect={"status": 200})],
        steps=[ProbeStep(operation="GetObjectAcl", key_suffix="acl/object.txt", expect={"status": 200})],
    )


def _versioning(required: bool) -> Probe:
    return Probe(
        id="versioning_behavior",
        family="versioning",
        required=required,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="versioning/object.txt", body="v1", expect={"status": 200})],
        steps=[
            ProbeStep(operation="GetBucketVersioning", expect={"status": 200}),
            ProbeStep(operation="ListObjectVersions", params={"prefix": "versioning/"}, expect={"status": 200}),
        ],
    )


def _multipart() -> Probe:
    return Probe(
        id="multipart_upload_small",
        family="multipart",
        required=True,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        requires_allow_multipart=True,
        steps=[
            ProbeStep(operation="CreateMultipartUpload", key_suffix="multipart/object.bin", expect={"status": 200}),
            ProbeStep(operation="UploadPart", key_suffix="multipart/object.bin", body="synthetic-part", params={"part_number": 1}, expect={"status": 200}),
            ProbeStep(operation="CompleteMultipartUpload", key_suffix="multipart/object.bin", expect={"status": 200}),
        ],
    )


def _presigned(hints: RequestHints) -> Probe:
    methods = hints.presigned.get("methods") or ["GET"]
    method = str(methods[0]).upper()
    return Probe(
        id=f"presigned_{method.lower()}",
        family="presigned",
        required=True,
        evidence_source=["REQUEST_HINTS"] if hints.presigned else ["CLOUDTRAIL"],
        requires_allow_writes=method in {"GET", "PUT"},
        setup=[ProbeStep(operation="PutObject", key_suffix="presigned/object.txt", body="presigned", expect={"status": 200})] if method == "GET" else [],
        steps=[ProbeStep(operation="PresignedUrl", key_suffix="presigned/object.txt", params={"method": method, "expires_in": hints.presigned.get("max_expiration_seconds", 300)}, expect={"status": 200})],
    )


def _cors_probes(hints: RequestHints, bucket_config: BucketConfig, required: bool) -> list[Probe]:
    cors = hints.cors or {}
    rules = (bucket_config.cors or {}).get("rules") or []
    first_rule = rules[0] if rules else {}
    origins = cors.get("origins") or first_rule.get("allowed_origins") or ["https://app.example.invalid"]
    methods = cors.get("methods") or first_rule.get("allowed_methods") or ["GET"]
    headers = cors.get("request_headers") or first_rule.get("allowed_headers") or []
    probes = []
    for origin in origins[:3]:
        for method in methods[:3]:
            probes.append(
                Probe(
                    id=f"cors_{str(method).lower()}_{stable_id(str(origin))}_preflight",
                    family="cors",
                    required=required,
                    evidence_source=["REQUEST_HINTS"] if hints.cors else ["BUCKET_CONFIG"],
                    steps=[
                        ProbeStep(
                            operation="CorsPreflight",
                            params={"origin": origin, "method": method, "request_headers": headers},
                            expect={"status": 200, "cors": {"origin": origin, "method": method, "request_headers": headers}},
                        )
                    ],
                )
            )
    return probes


def _conditional_requests() -> Probe:
    return Probe(
        id="conditional_get_if_match",
        family="conditional_requests",
        required=True,
        evidence_source=["REQUEST_HINTS"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="conditional/object.txt", body="conditional", expect={"status": 200})],
        steps=[
            ProbeStep(operation="ConditionalGetObject", key_suffix="conditional/object.txt", params={"if_match": "setup-etag", "if_none_match": "*"}, expect={"status": 200})
        ],
    )


def _range_get() -> Probe:
    return Probe(
        id="range_get_bytes",
        family="range_gets",
        required=True,
        evidence_source=["REQUEST_HINTS"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="range/object.bin", body="0123456789", expect={"status": 200})],
        steps=[ProbeStep(operation="GetObjectRange", key_suffix="range/object.bin", params={"range": "bytes=0-3"}, expect={"status": 206, "body_length": 4})],
    )


def _metadata_roundtrip(hints: RequestHints) -> Probe:
    metadata = {header.replace("x-amz-meta-", ""): "value" for header in hints.metadata_headers[:5]} or {"client-id": "value"}
    return Probe(
        id="metadata_header_roundtrip",
        family="metadata",
        required=True,
        evidence_source=["REQUEST_HINTS"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="metadata/object.txt", body="metadata", metadata=metadata, expect={"status": 200})],
        steps=[ProbeStep(operation="HeadObject", key_suffix="metadata/object.txt", expect={"status": 200, "metadata": metadata})],
    )


def _encryption_headers() -> Probe:
    return Probe(
        id="encryption_header_basic",
        family="encryption_headers",
        required=False,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObjectEncryption", key_suffix="encryption/object.txt", body="encrypted", params={"server_side_encryption": "AES256"}, expect={"status": 200})],
        steps=[ProbeStep(operation="HeadObject", key_suffix="encryption/object.txt", expect={"status": 200, "headers": {"x-amz-server-side-encryption": "AES256"}})],
    )


def _presigned_expiry(hints: RequestHints) -> Probe:
    buckets = hints.presigned_expiration_buckets or [60, 3600]
    return Probe(
        id="presigned_expiry_boundaries",
        family="presigned_expiry",
        required=True,
        evidence_source=["REQUEST_HINTS"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="presigned-expiry/object.txt", body="presigned", expect={"status": 200})],
        steps=[ProbeStep(operation="PresignedExpiryBoundary", key_suffix="presigned-expiry/object.txt", params={"method": "GET", "expiration_buckets": buckets}, expect={"status": 200})],
    )


def _list_pagination() -> Probe:
    return Probe(
        id="list_pagination_tokens",
        family="list_pagination",
        required=True,
        evidence_source=["REQUEST_HINTS"],
        requires_allow_writes=True,
        setup=[
            ProbeStep(operation="PutObject", key_suffix="pagination/a.txt", body="a", expect={"status": 200}),
            ProbeStep(operation="PutObject", key_suffix="pagination/b.txt", body="b", expect={"status": 200}),
        ],
        steps=[ProbeStep(operation="ListObjectsV2Pagination", params={"prefix": "pagination/", "max_keys": 1}, expect={"status": 200, "continuation_token_present": True})],
    )


def _versioning_delete_marker() -> Probe:
    return Probe(
        id="versioning_delete_marker",
        family="versioning_delete_marker",
        required=True,
        evidence_source=["CLOUDTRAIL"],
        requires_allow_writes=True,
        requires_allow_deletes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="version-delete/object.txt", body="v1", expect={"status": 200})],
        steps=[
            ProbeStep(operation="DeleteObject", key_suffix="version-delete/object.txt", expect={"status": 204}),
            ProbeStep(operation="ListObjectVersions", params={"prefix": "version-delete/"}, expect={"status": 200, "delete_marker_present": True}),
        ],
    )


def _consistency_probe() -> Probe:
    return Probe(
        id="read_list_after_write_consistency",
        family="consistency",
        required=False,
        evidence_source=["REQUEST_HINTS"],
        requires_allow_writes=True,
        setup=[ProbeStep(operation="PutObject", key_suffix="consistency/object.txt", body="consistent", expect={"status": 200})],
        steps=[
            ProbeStep(operation="HeadObject", key_suffix="consistency/object.txt", expect={"status": 200}),
            ProbeStep(operation="GetObject", key_suffix="consistency/object.txt", expect={"status": 200, "body_sha256_matches_setup": True}),
            ProbeStep(operation="ListObjectsV2", params={"prefix": "consistency/", "max_keys": 1000}, expect={"status": 200}),
        ],
    )


def _authz_context_review() -> Probe:
    return Probe(
        id="authz_policy_context_review",
        family="authz_context",
        required=False,
        evidence_source=["BUCKET_CONFIG"],
        steps=[ProbeStep(operation="PolicyContextReview", expect={"status": "REVIEW"})],
    )


def _ownership_controls() -> Probe:
    return Probe(
        id="ownership_controls_check",
        family="ownership_controls",
        required=False,
        evidence_source=["BUCKET_CONFIG"],
        steps=[ProbeStep(operation="GetBucketOwnershipControls", expect={"status": 200})],
    )


def _requester_pays() -> Probe:
    return Probe(
        id="requester_pays_header",
        family="requester_pays",
        required=False,
        evidence_source=["REQUEST_HINTS"],
        steps=[ProbeStep(operation="RequesterPaysList", params={"prefix": "", "max_keys": 1}, expect={"status": 200})],
    )


def _object_lock(required: bool) -> Probe:
    return Probe(
        id="object_lock_static_or_lab",
        family="object_lock",
        required=required,
        evidence_source=["BUCKET_CONFIG"],
        requires_allow_writes=True,
        requires_allow_object_lock_tests=True,
        warnings=["OBJECT_LOCK_REQUIRES_BUCKET_SUPPORT"],
        setup=[ProbeStep(operation="PutObject", key_suffix="object-lock/object.txt", body="lock", expect={"status": 200})],
        steps=[ProbeStep(operation="PutObjectRetention", key_suffix="object-lock/object.txt", params={"mode": "GOVERNANCE", "retain_days": 1}, expect={"status": 200})],
    )


def _lifecycle_static() -> Probe:
    return Probe(
        id="lifecycle_static_review",
        family="lifecycle",
        required=False,
        evidence_source=["BUCKET_CONFIG"],
        warnings=["LIFECYCLE_STATIC_ONLY"],
        steps=[ProbeStep(operation="LifecycleValidationPlan", expect={"status": "REVIEW", "mismatch_code": "LIFECYCLE_NOT_TESTED"})],
    )


def stable_id(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
