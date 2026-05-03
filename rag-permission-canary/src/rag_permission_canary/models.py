"""Typed models for canary fixtures, packs, endpoint profiles, and results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Access = Literal["ALLOWED", "FORBIDDEN", "UNKNOWN"]
ResultStatus = Literal["PASS", "FAIL", "REVIEW", "SKIPPED"]
AggregateStatus = Literal["PASS", "FAIL", "REVIEW", "INSUFFICIENT_DATA"]


class Canary(BaseModel):
    canary_id: str
    type: str = "exact_span"
    text: str
    description: str = ""


class Document(BaseModel):
    doc_id: str
    title: str
    collection: str = ""
    sensitivity: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    body: str
    canaries: list[Canary] = Field(default_factory=list)


class ContentSet(BaseModel):
    content_set_id: str
    content_set_version: int | str = 1
    description: str = ""
    documents: list[Document]


class UserAuth(BaseModel):
    type: Literal["bearer_env", "header_env", "none"]
    token_env: str = ""
    header_name: str = "Authorization"
    header_value_env: str = ""


class TestUser(BaseModel):
    user_id: str
    display_name: str = ""
    auth: UserAuth = Field(default_factory=lambda: UserAuth(type="none"))
    groups: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TestUsers(BaseModel):
    users: list[TestUser]


class PermissionRule(BaseModel):
    subject_type: Literal["group", "user", "attribute"] = "group"
    subject: str = ""
    access: Literal["allow", "deny"]
    documents: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionModel(BaseModel):
    permission_model: Literal["group_acl", "user_acl", "attribute_acl"]
    default_access: Literal["allow", "deny"] = "deny"
    grants: list[PermissionRule] = Field(default_factory=list)
    denies: list[PermissionRule] = Field(default_factory=list)


class RequestTemplate(BaseModel):
    method: str = "POST"
    path: str = "/query"
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: dict[str, Any]


class EndpointAuth(BaseModel):
    user_auth_from_test_user: bool = True
    type: Literal["none", "bearer_env", "header_env"] = "none"
    token_env: str = ""
    header_name: str = "Authorization"
    header_value_env: str = ""


class ResponseExtractors(BaseModel):
    answer_text_json_path: str = "$.answer"
    citations_json_path: str = "$.citations"
    citation_doc_id_json_path: str = "$.doc_id"
    citation_title_json_path: str = "$.title"
    citation_snippet_json_path: str = "$.snippet"
    metadata_json_path: str = "$.metadata"
    raw_context_json_path: str = "$.retrieved_context"


class EndpointBehavior(BaseModel):
    expected_forbidden_response: dict[str, Any] = Field(default_factory=dict)
    require_citations_for_allowed: bool = False
    fail_on_forbidden_citation_doc_id: bool = True
    fail_on_forbidden_title: bool = True
    fail_on_forbidden_metadata: bool = True
    fail_on_forbidden_snippet: bool = True
    fail_on_forbidden_summary: bool = True


class EndpointProfile(BaseModel):
    endpoint_id: str
    base_url: str
    local_test_only: bool = False
    request: RequestTemplate
    auth: EndpointAuth = Field(default_factory=EndpointAuth)
    response_extractors: ResponseExtractors = Field(default_factory=ResponseExtractors)
    behavior: EndpointBehavior = Field(default_factory=EndpointBehavior)


class LeakageCheck(BaseModel):
    forbidden_canary_texts: list[str] = Field(default_factory=list)
    forbidden_doc_titles: list[str] = Field(default_factory=list)
    forbidden_metadata_values: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)


class CanaryTestCase(BaseModel):
    test_case_id: str
    user_id: str
    query: str
    expected_result: Access
    target_doc_id: str
    target_canary_ids: list[str] = Field(default_factory=list)
    target_canary_texts: list[str] = Field(default_factory=list)
    forbidden_doc_ids: list[str] = Field(default_factory=list)
    allowed_doc_ids: list[str] = Field(default_factory=list)
    leakage_checks: LeakageCheck = Field(default_factory=LeakageCheck)
    reason_codes: list[str] = Field(default_factory=list)


class CanaryPack(BaseModel):
    pack_id: str
    generated_at: str
    content_set_id: str
    users: list[str]
    test_users: list[TestUser] = Field(default_factory=list)
    test_cases: list[CanaryTestCase]
    warnings: list[str] = Field(default_factory=list)


class ExtractedResponse(BaseModel):
    answer_text: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    citation_doc_ids: list[str] = Field(default_factory=list)
    citation_titles: list[str] = Field(default_factory=list)
    citation_snippets: list[str] = Field(default_factory=list)
    metadata_values: list[str] = Field(default_factory=list)
    raw_context: str = ""
    warnings: list[str] = Field(default_factory=list)


class EndpointResponse(BaseModel):
    http_status: int = 0
    latency_ms: int = 0
    json_body: Any = None
    text_body: str = ""
    error: str = ""
    warnings: list[str] = Field(default_factory=list)


class LeakageFinding(BaseModel):
    leakage_type: str
    forbidden_doc_id: str = ""
    canary_id: str = ""
    redacted_evidence: str = ""
    severity: str = "CRITICAL"


class TestResult(BaseModel):
    test_case_id: str
    user_id: str
    expected_result: Access
    status: ResultStatus
    http_status: int = 0
    latency_ms: int = 0
    target_doc_id: str = ""
    leakage_findings: list[LeakageFinding] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    answer_excerpt_redacted: str = ""
    citation_doc_ids_redacted: list[str] = Field(default_factory=list)


class RunResults(BaseModel):
    run_id: str
    pack_id: str
    content_set_id: str
    endpoint_id: str
    started_at: str
    finished_at: str
    aggregate_status: AggregateStatus
    summary: dict[str, int] = Field(default_factory=dict)
    leakage_summary: dict[str, int] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    business_context: dict[str, Any] = Field(default_factory=dict)
    test_results: list[TestResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
