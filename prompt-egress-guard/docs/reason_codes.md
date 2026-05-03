# Reason Codes

Reason codes are deterministic and stable. They are intended for local audit summaries, user overlays, and policy testing.

Core reason codes:

- `PROMPT_SCANNED`
- `PROMPT_EMPTY`
- `PROMPT_INPUT_NOT_FOUND`
- `PROMPT_TRUNCATED_FOR_SCAN`
- `POLICY_MODE_OBSERVE`
- `POLICY_MODE_WARN`
- `POLICY_MODE_ENFORCE`
- `ACTION_ALLOW`
- `ACTION_WARN`
- `ACTION_REDIRECT`
- `ACTION_BLOCK`
- `USER_CONFIRMED_WARN_CONTINUE`
- `APPROVED_ENDPOINT_REDIRECT_RECOMMENDED`
- `APPROVED_DESTINATION_OPENED`
- `APPROVED_DESTINATION_MISSING`
- `CLIPBOARD_COPY_REQUESTED`
- `RAW_PROMPT_STORAGE_DISABLED`
- `LOCAL_AUDIT_EVENT_WRITTEN`
- `REVIEW_ONLY_AUDIT_EXPORT`

Detector reason codes include secret-like, source-code-like, customer-record-like, health-data-like, legal-sensitive, internal-identifier, personal-data-like, and financial-sensitive pattern matches. The canonical list lives in `packages/core/src/reason_codes.ts`.

Warnings:

- `PROMPT_INPUT_NOT_FOUND`
- `MULTIPLE_PROMPT_INPUTS_FOUND`
- `SUBMIT_INTERCEPT_HEURISTIC_USED`
- `SITE_SELECTOR_MAY_BE_STALE`
- `PROMPT_TRUNCATED_FOR_SCAN`
- `LOW_CONFIDENCE_MATCH`
- `HIGH_FALSE_POSITIVE_RISK`
- `APPROVED_DESTINATION_MISSING`
- `DNR_CONTENT_INSPECTION_NOT_AVAILABLE`
- `BROAD_HOST_PERMISSION_REQUESTED`
- `CLIPBOARD_COPY_ALLOWED_BY_POLICY`
- `LOCAL_AUDIT_RETENTION_LIMIT_REACHED`
- `OBSERVE_MODE_NO_ENFORCEMENT`
- `REDACTION_ENABLED`

Blockers:

- `POLICY_INVALID`
- `MONITORED_SITE_MISSING`
- `HOST_PERMISSION_INVALID`
- `APPROVED_DESTINATION_INVALID`
- `UNSAFE_PROMPT_TRANSFER_WITHOUT_ACK`
- `RAW_PROMPT_STORAGE_WITHOUT_ACK`
- `UNSAFE_BROAD_HOST_PERMISSIONS_WITHOUT_ACK`
- `THRESHOLDS_INVALID`
- `CATEGORY_ACTION_INVALID`
- `EXTENSION_BUILD_FAILED`
- `MANIFEST_GENERATION_FAILED`

Pilot gap codes use `INPUT_*` and `OUTPUT_*` prefixes in `pilot_assessment.json`. They identify evidence gaps, not detector findings.

Do not infer intent from a reason code. A detector reason code means a sensitive-pattern match occurred, not that the user acted maliciously or that compliance was proven.
