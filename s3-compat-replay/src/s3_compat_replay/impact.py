from __future__ import annotations


BUSINESS_IMPACT_BY_CODE = {
    "PRESIGNED_URL_FAILED": "External download or upload links may fail after cutover.",
    "CORS_PREFLIGHT_MISMATCH": "Browser flows may fail even if server-side SDK traffic works.",
    "VERSIONING_TARGET_NOT_ENABLED": "Application logic or tooling that expects version IDs may fail.",
    "VERSION_ID_BEHAVIOR_MISMATCH": "Application logic or tooling that expects version IDs may behave differently.",
    "TAGGING_ROUNDTRIP_FAILED": "Workflows depending on object tags may fail or misroute objects.",
    "METADATA_ROUNDTRIP_FAILED": "Applications that route, classify, or validate objects using metadata may fail.",
    "ACL_UNSUPPORTED_OR_DISABLED": "Workflows depending on ACL calls may need review or changes.",
    "BASIC_WRITE_READ_FAILED": "Basic synthetic object write/read/head behavior failed.",
    "COPY_OBJECT_FAILED": "Server-side copy workflows may fail or require application-side copy changes.",
    "MULTIPART_CREATE_FAILED": "Large ingest, backup, or data lake writers may fail during multipart setup.",
    "MULTIPART_UPLOAD_FAILED": "Large ingest, backup, or data lake writers may fail while uploading multipart data.",
    "MULTIPART_COMPLETE_FAILED": "Large ingest, backup, or data lake writers may fail during multipart completion.",
    "MULTIPART_ABORT_FAILED": "Failed multipart writes may leave incomplete upload state that operations must clean up.",
    "OBJECT_LOCK_UNSUPPORTED": "Retention, legal hold, or audit workflows may not be enforceable on the target scratch bucket.",
    "OBJECT_LOCK_RETENTION_MISMATCH": "Retention periods or modes may not match the workflow's records requirements.",
    "OBJECT_LOCK_LEGAL_HOLD_MISMATCH": "Legal-hold workflows may not preserve expected hold behavior.",
    "DELETE_MARKER_BEHAVIOR_MISMATCH": "Recovery, audit, or cleanup workflows that rely on delete markers may behave differently.",
    "LIFECYCLE_NOT_TESTED": "Lifecycle expiration or transition side effects require separate human validation.",
    "LIST_PAGINATION_TOKEN_MISSING": "Large prefix listing workflows may fail or silently miss objects.",
    "CONDITIONAL_REQUEST_MISMATCH": "Optimistic concurrency or cache validation flows may behave differently.",
    "RANGE_GET_MISMATCH": "Media, resumable download, or partial-read clients may fail.",
    "ENCRYPTION_HEADER_MISMATCH": "Workloads that inspect encryption response headers may need review.",
    "PRESIGNED_EXPIRY_MISMATCH": "External links may expire too early or remain valid longer than expected.",
    "CONSISTENCY_MODEL_MISMATCH": "Applications assuming immediate read/list visibility may fail intermittently.",
    "REQUESTER_PAYS_MISMATCH": "Clients that require requester-pays headers may fail.",
    "OWNERSHIP_CONTROLS_MISMATCH": "Object ownership or ACL remediation assumptions may need review.",
    "AUTHZ_CONTEXT_REVIEW_REQUIRED": "Authorization failures may need policy-owner review before remediation.",
    "STATUS_CODE_MISMATCH": "A required S3-style operation returned a different status than the workload expectation.",
    "ERROR_CODE_MISMATCH": "Clients that branch on S3-style error codes may behave differently.",
    "CRITICAL_HEADER_MISSING": "Clients that inspect response headers may lose routing, validation, or security evidence.",
    "CRITICAL_HEADER_VALUE_MISMATCH": "Clients that inspect response header values may make the wrong routing or validation decision.",
    "RESPONSE_BODY_HASH_MISMATCH": "Synthetic object body behavior did not match the expected read-back behavior.",
}


QUESTION_BY_CODE = {
    "PRESIGNED_URL_FAILED": "Does the application rely on presigned URLs for external downloads or uploads?",
    "CORS_PREFLIGHT_MISMATCH": "Which browser origins, methods, and headers must be supported?",
    "VERSIONING_TARGET_NOT_ENABLED": "Is versionId behavior required by application logic or only by operations tooling?",
    "VERSION_ID_BEHAVIOR_MISMATCH": "Which code or tooling paths depend on version IDs?",
    "TAGGING_ROUNDTRIP_FAILED": "Which object tags are required by application logic?",
    "METADATA_ROUNDTRIP_FAILED": "Which metadata headers are required for routing, classification, or validation?",
    "ACL_UNSUPPORTED_OR_DISABLED": "Does the application require ACLs or are ACL calls incidental?",
    "BASIC_WRITE_READ_FAILED": "Can the target bucket perform basic synthetic PutObject, HeadObject, and GetObject calls?",
    "COPY_OBJECT_FAILED": "Which workflows rely on server-side copy rather than application-side read and write?",
    "MULTIPART_CREATE_FAILED": "Which large writers depend on multipart setup behavior?",
    "MULTIPART_UPLOAD_FAILED": "What multipart part sizes and retry behavior must writers support?",
    "MULTIPART_COMPLETE_FAILED": "What object size ranges and multipart part sizes must writers support?",
    "MULTIPART_ABORT_FAILED": "How are incomplete multipart uploads detected and cleaned up?",
    "OBJECT_LOCK_UNSUPPORTED": "Which retention and legal hold behaviors must be validated in an explicitly enabled scratch bucket?",
    "OBJECT_LOCK_RETENTION_MISMATCH": "Which retention modes and durations are required for this workload?",
    "OBJECT_LOCK_LEGAL_HOLD_MISMATCH": "Which legal-hold workflows are in scope for cutover?",
    "DELETE_MARKER_BEHAVIOR_MISMATCH": "Does application or operations tooling depend on delete markers for recovery or audit?",
    "LIFECYCLE_NOT_TESTED": "Which lifecycle side effects must be validated outside this short replay?",
    "LIST_PAGINATION_TOKEN_MISSING": "How large are production listings and do clients depend on continuation tokens?",
    "CONDITIONAL_REQUEST_MISMATCH": "Which clients rely on If-Match or If-None-Match semantics?",
    "RANGE_GET_MISMATCH": "Which clients rely on partial reads or resumable downloads?",
    "ENCRYPTION_HEADER_MISMATCH": "Do applications inspect encryption headers or only require encryption at rest?",
    "PRESIGNED_EXPIRY_MISMATCH": "What presigned URL expiration ranges are required by external flows?",
    "CONSISTENCY_MODEL_MISMATCH": "Which flows assume immediate visibility after write or delete?",
    "REQUESTER_PAYS_MISMATCH": "Which clients send requester-pays headers and for which operations?",
    "OWNERSHIP_CONTROLS_MISMATCH": "Are ACL calls required or should ownership controls replace them?",
    "AUTHZ_CONTEXT_REVIEW_REQUIRED": "Which policy owner can confirm whether failures are authorization or semantic mismatches?",
    "STATUS_CODE_MISMATCH": "Which application behavior depends on this status code?",
    "ERROR_CODE_MISMATCH": "Which clients branch on this error code?",
    "CRITICAL_HEADER_MISSING": "Which clients inspect this response header?",
    "CRITICAL_HEADER_VALUE_MISMATCH": "Which clients require this response header value?",
    "RESPONSE_BODY_HASH_MISMATCH": "Which client paths depend on byte-identical read-back behavior?",
}


def business_impact_for_code(code: str) -> str:
    return BUSINESS_IMPACT_BY_CODE.get(code, "Observed object-storage behavior may differ from the source workload expectation.")


def question_for_code(code: str) -> str:
    return QUESTION_BY_CODE.get(code, "Which application behavior depends on this S3 API detail?")
