"""Output column contracts."""

CANARY_QUERY_COLUMNS = [
    "test_case_id",
    "user_id",
    "expected_result",
    "target_doc_id",
    "target_canary_ids",
    "query",
    "allowed_doc_ids",
    "forbidden_doc_ids",
    "forbidden_canary_count",
    "forbidden_title_count",
    "forbidden_metadata_count",
    "reason_codes",
]

SAMPLES_COLUMNS = [
    "test_case_id",
    "user_id",
    "expected_result",
    "status",
    "http_status",
    "latency_ms",
    "target_doc_id",
    "leaked_forbidden_doc_ids",
    "leaked_forbidden_canary_ids",
    "citation_doc_ids_redacted",
    "answer_excerpt_redacted",
    "reason_codes",
    "warnings",
]
