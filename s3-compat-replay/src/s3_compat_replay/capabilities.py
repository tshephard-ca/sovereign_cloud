from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityDefinition:
    capability: str
    business_flow: str
    owner_role: str
    why_it_matters: str
    next_action: str


CAPABILITY_BY_FAMILY: dict[str, CapabilityDefinition] = {
    "object_read": CapabilityDefinition("basic read/write/head", "core object access", "storage architect", "Applications must be able to write, read, and inspect synthetic objects before any higher-level workflow is meaningful.", "Confirm basic object operations and error shapes on the target scratch bucket."),
    "object_write": CapabilityDefinition("server-side copy", "server-side object processing", "application developer", "CopyObject-dependent workflows can break even when normal upload and download work.", "Identify workflows that rely on server-side copy and decide whether target support or application-side copy is required."),
    "object_delete": CapabilityDefinition("delete behavior", "cleanup and lifecycle preparation", "storage architect", "Delete semantics affect cleanup, temporary files, and recovery expectations.", "Confirm whether delete calls are required in cutover scope and whether delete probes can be approved."),
    "object_list": CapabilityDefinition("prefix listing", "batch discovery and object enumeration", "data platform owner", "List semantics determine whether batch jobs and inventories can find the objects they expect.", "Validate prefix, delimiter, and listing behavior against production list shapes."),
    "tagging": CapabilityDefinition("object tag round trip", "tag-driven routing and governance", "application owner", "Tags often drive workflow routing, retention class, lifecycle behavior, and access decisions.", "Confirm required tag keys and remediate target tag behavior before cutover."),
    "acl": CapabilityDefinition("ACL and ownership behavior", "security posture and legacy ACL compatibility", "security architect", "ACL calls may be intentional application behavior or legacy noise that should be retired.", "Decide whether ACL calls are required or can be replaced by ownership controls and policy."),
    "versioning": CapabilityDefinition("version ID behavior", "recovery, support, and audit", "support operations lead", "Version IDs and object versions are often used for restore, investigation, and audit tooling.", "Confirm whether version IDs are application-critical or only operations tooling context."),
    "versioning_delete_marker": CapabilityDefinition("delete marker behavior", "version-aware recovery", "support operations lead", "Delete markers change how deleted objects are recovered and audited.", "Validate delete-marker expectations for restore and support workflows."),
    "multipart": CapabilityDefinition("multipart completion", "large ingest and archive writers", "data platform owner", "Large-object writers can fail at multipart completion even when small object tests pass.", "Confirm object size ranges, part sizes, and multipart completion semantics."),
    "presigned": CapabilityDefinition("presigned URL access", "external upload/download links", "web product owner", "External users and partner flows often depend on presigned URL behavior rather than direct SDK calls.", "Validate presigned GET/PUT flows and identify external user journeys that depend on them."),
    "presigned_expiry": CapabilityDefinition("presigned expiration boundaries", "external link validity windows", "web product owner", "Links expiring too early or too late can cause customer failure or access risk.", "Confirm required expiration buckets and target boundary behavior."),
    "cors": CapabilityDefinition("browser CORS preflight", "browser upload/download", "web product owner", "Browser flows can fail even when server-side SDK traffic succeeds.", "Confirm every required origin, method, and request-header group."),
    "conditional_requests": CapabilityDefinition("conditional requests", "cache validation and optimistic concurrency", "application developer", "If-Match and If-None-Match behavior protects cache validation and optimistic concurrency flows.", "Identify clients that depend on conditional requests and validate target behavior."),
    "range_gets": CapabilityDefinition("range reads", "partial reads and resumable download", "application developer", "Range behavior affects media, partial readers, and resumable download clients.", "Confirm byte-range requirements and target response semantics."),
    "metadata": CapabilityDefinition("metadata round trip", "metadata-driven routing and validation", "application owner", "Applications often read metadata after writes for routing, classification, or validation.", "Confirm required metadata headers and target round-trip behavior."),
    "encryption_headers": CapabilityDefinition("encryption response headers", "security evidence and SDK expectations", "security architect", "Some workloads inspect encryption headers as operational or security evidence.", "Decide whether applications inspect headers or only require encryption at rest."),
    "object_lock": CapabilityDefinition("Object Lock and retention", "retention, legal hold, and audit", "compliance lead", "Retention and legal-hold workflows require target support before regulated data moves.", "Validate Object Lock in an explicitly enabled scratch bucket and confirm retention requirements."),
    "list_pagination": CapabilityDefinition("list pagination tokens", "large prefix enumeration", "data platform owner", "Large listings can silently miss objects if continuation-token behavior differs.", "Validate bounded pagination against representative list patterns."),
    "consistency": CapabilityDefinition("read/list consistency", "write-after-read workflow correctness", "application owner", "Applications may assume immediate visibility after write or delete.", "Confirm which flows assume immediate read/list visibility."),
    "authz_context": CapabilityDefinition("authorization context", "policy ownership and remediation routing", "security architect", "Authorization denials can be mistaken for target semantic gaps without policy context.", "Route failures to the policy owner before changing application code."),
    "ownership_controls": CapabilityDefinition("ownership controls", "bucket-owner-enforced posture", "security architect", "Ownership controls affect ACL retirement and cross-account write assumptions.", "Map ACL expectations to ownership-control posture."),
    "requester_pays": CapabilityDefinition("requester-pays headers", "payer-aware client behavior", "application owner", "Clients that need payer headers can fail if the target rejects or ignores them.", "Confirm which clients send requester-pays headers and for which operations."),
    "lifecycle": CapabilityDefinition("lifecycle static review", "expiration and transition operations", "storage architect", "Lifecycle behavior cannot be proven by a short replay but may affect cleanup and archival expectations.", "Create a separate lifecycle validation plan for time-based effects."),
}


FAMILY_BY_MISMATCH_CODE: dict[str, str] = {
    "COPY_OBJECT_FAILED": "object_write",
    "TAGGING_ROUNDTRIP_FAILED": "tagging",
    "ACL_UNSUPPORTED_OR_DISABLED": "acl",
    "VERSIONING_TARGET_NOT_ENABLED": "versioning",
    "VERSION_ID_BEHAVIOR_MISMATCH": "versioning",
    "DELETE_MARKER_BEHAVIOR_MISMATCH": "versioning_delete_marker",
    "MULTIPART_CREATE_FAILED": "multipart",
    "MULTIPART_UPLOAD_FAILED": "multipart",
    "MULTIPART_COMPLETE_FAILED": "multipart",
    "MULTIPART_ABORT_FAILED": "multipart",
    "PRESIGNED_URL_FAILED": "presigned",
    "PRESIGNED_URL_HEADER_MISMATCH": "presigned",
    "CORS_PREFLIGHT_MISMATCH": "cors",
    "CONDITIONAL_REQUEST_MISMATCH": "conditional_requests",
    "RANGE_GET_MISMATCH": "range_gets",
    "METADATA_ROUNDTRIP_FAILED": "metadata",
    "ENCRYPTION_HEADER_MISMATCH": "encryption_headers",
    "OBJECT_LOCK_UNSUPPORTED": "object_lock",
    "OBJECT_LOCK_RETENTION_MISMATCH": "object_lock",
    "OBJECT_LOCK_LEGAL_HOLD_MISMATCH": "object_lock",
    "PRESIGNED_EXPIRY_MISMATCH": "presigned_expiry",
    "LIST_PAGINATION_TOKEN_MISSING": "list_pagination",
    "CONSISTENCY_MODEL_MISMATCH": "consistency",
    "AUTHZ_CONTEXT_REVIEW_REQUIRED": "authz_context",
    "OWNERSHIP_CONTROLS_MISMATCH": "ownership_controls",
    "REQUESTER_PAYS_MISMATCH": "requester_pays",
    "LIFECYCLE_NOT_TESTED": "lifecycle",
    "BASIC_WRITE_READ_FAILED": "object_read",
    "STATUS_CODE_MISMATCH": "object_read",
    "ERROR_CODE_MISMATCH": "object_read",
    "CRITICAL_HEADER_MISSING": "object_read",
    "CRITICAL_HEADER_VALUE_MISMATCH": "object_read",
    "RESPONSE_BODY_HASH_MISMATCH": "object_read",
}


FEATURE_FAMILY: dict[str, str] = {
    "ACL": "acl",
    "BODY_CLASSES": "object_read",
    "CONDITIONAL_REQUESTS": "conditional_requests",
    "CONSISTENCY_EXPECTATIONS": "consistency",
    "CONTENT_TYPES": "object_write",
    "CORS": "cors",
    "ENCRYPTION_CONFIG": "encryption_headers",
    "ENCRYPTION_HEADERS": "encryption_headers",
    "EVENT_NOTIFICATIONS": "authz_context",
    "LIFECYCLE": "lifecycle",
    "METADATA_HEADERS": "metadata",
    "MULTIPART": "multipart",
    "OBJECT_LOCK": "object_lock",
    "OBJECT_SIZE_DISTRIBUTION": "multipart",
    "OBJECT_TAGGING": "tagging",
    "OWNERSHIP_CONTROLS": "ownership_controls",
    "PAGINATION_TOKENS": "list_pagination",
    "POLICY_CONTEXT": "authz_context",
    "PRESIGNED_EXPIRATION_BUCKETS": "presigned_expiry",
    "PRESIGNED_OBSERVED": "presigned",
    "RANGE_GETS": "range_gets",
    "REPLICATION": "lifecycle",
    "REQUESTER_PAYS": "requester_pays",
    "REQUESTER_PAYS_TRAFFIC": "requester_pays",
    "SIGNATURE_VERSION_OBSERVED": "object_read",
    "VERSIONING": "versioning",
    "VERSION_ID": "versioning",
}


def capability_for_family(family: str) -> CapabilityDefinition:
    return CAPABILITY_BY_FAMILY.get(
        family,
        CapabilityDefinition(
            capability=family.replace("_", " "),
            business_flow="object-storage application behavior",
            owner_role="storage architect",
            why_it_matters="Observed object-storage behavior may affect cutover readiness.",
            next_action="Review this behavior with the application owner and storage architect.",
        ),
    )


def family_for_mismatch_code(code: str, fallback_family: str = "object_read") -> str:
    return FAMILY_BY_MISMATCH_CODE.get(code, fallback_family)


def family_for_feature(feature: str) -> str:
    return FEATURE_FAMILY.get(feature, "object_read")
