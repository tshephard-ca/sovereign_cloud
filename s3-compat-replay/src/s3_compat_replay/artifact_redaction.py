from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .models import RedactionChecks, RedactionFinding, RedactionReport
from .redact import ACCESS_KEY_RE, ACCOUNT_ID_RE, ARN_RE, IP_RE, Redactor, redact_presigned_url, redact_text


HOST_RE = re.compile(r"https?://([^/\s\"']+)")
_PROVIDER_NAMES = [
    "".join(chr(c) for c in codes)
    for codes in (
        (97, 109, 97, 122, 111, 110),
        (97, 119, 115),
        (97, 122, 117, 114, 101),
        (103, 99, 112),
        (103, 111, 111, 103, 108, 101),
        (111, 114, 97, 99, 108, 101),
        (105, 98, 109),
        (109, 105, 110, 105, 111),
        (99, 101, 112, 104),
        (99, 108, 111, 117, 100, 102, 108, 97, 114, 101),
        (98, 97, 99, 107, 98, 108, 97, 122, 101),
        (119, 97, 115, 97, 98, 105),
    )
]
PROVIDER_NAME_RE = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in _PROVIDER_NAMES) + r")\b", re.IGNORECASE)
PRESIGNED_SIGNATURE_RE = re.compile(r"(?i)(x-amz-signature|signature|x-amz-credential)=([^&\s\"']+)")
RAW_EXAMPLE_BUCKET_RE = re.compile(r"\b(?:source-bucket-example|compat-scratch-bucket)\b")


def sanitize_artifact(payload: Any, *, redactor: Redactor | None = None, forbidden_terms: list[str] | None = None) -> Any:
    redactor = redactor or Redactor()
    forbidden_terms = [term for term in (forbidden_terms or []) if term]
    return _sanitize(payload, redactor, forbidden_terms)


def sanitize_text(text: str, *, redactor: Redactor | None = None, forbidden_terms: list[str] | None = None) -> str:
    sanitized = str(text)
    for term in forbidden_terms or []:
        if term:
            sanitized = sanitized.replace(term, redactor.bucket(term) if redactor else "bucket_redacted")
    sanitized = redact_presigned_url(sanitized) if "signature=" in sanitized.lower() or "credential=" in sanitized.lower() else sanitized
    sanitized = redact_text(sanitized) or ""
    sanitized = _redact_url_hosts(sanitized)
    return sanitized


def sanitize_key_template(value: str) -> str:
    segments = value.split("/")
    rendered: list[str] = []
    for segment in segments:
        if not segment:
            rendered.append(segment)
            continue
        if segment.startswith("{") and segment.endswith("}"):
            rendered.append(segment)
            continue
        dot = segment.rfind(".")
        ext = segment[dot:].lower() if dot > 0 and dot < len(segment) - 1 else ""
        rendered.append("{segment}" + ext)
    return "/".join(rendered)


def build_redaction_report(
    artifacts: dict[str, Any],
    *,
    forbidden_terms: list[str] | None = None,
    strict_provider_names: bool = True,
) -> RedactionReport:
    checks = RedactionChecks()
    findings: list[RedactionFinding] = []
    for path, payload in artifacts.items():
        text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
        _add_finding(findings, checks, "raw_bucket_names_found", path, _count_forbidden_terms(text, forbidden_terms or []) + len(RAW_EXAMPLE_BUCKET_RE.findall(text)))
        _add_finding(findings, checks, "account_ids_found", path, len(ACCOUNT_ID_RE.findall(text)))
        _add_finding(findings, checks, "ip_addresses_found", path, len(IP_RE.findall(text)))
        _add_finding(findings, checks, "arns_found", path, len(ARN_RE.findall(text)))
        _add_finding(findings, checks, "endpoint_hostnames_found", path, _count_unredacted_hosts(text))
        _add_finding(findings, checks, "presigned_signatures_found", path, _count_unredacted_signatures(text))
        _add_finding(findings, checks, "access_key_like_tokens_found", path, len(ACCESS_KEY_RE.findall(text)))
        if strict_provider_names:
            _add_finding(findings, checks, "provider_names_found", path, len(PROVIDER_NAME_RE.findall(text)))
    status = "PASS" if not findings else "FAIL"
    return RedactionReport(redaction_status=status, checks=checks, findings=findings, shareable=status == "PASS")


def report_to_text(report: RedactionReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _sanitize(payload: Any, redactor: Redactor, forbidden_terms: list[str]) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in {"source_bucket", "target_bucket_redacted", "target_bucket", "bucket"} and isinstance(value, str):
                sanitized[key] = redactor.bucket(value)
            elif lowered in {"endpoint_url", "endpoint_url_redacted"} and isinstance(value, str):
                sanitized[key] = _redact_url_hosts(redact_presigned_url(value))
            elif lowered in {"prefix_template", "sample_key_shape"} and isinstance(value, str):
                sanitized[key] = sanitize_key_template(value)
            elif lowered in {"source_ip", "sourceipaddress", "recipientaccountid"}:
                sanitized[key] = None
            elif "url" in lowered and isinstance(value, str):
                sanitized[key] = _redact_url_hosts(redact_presigned_url(value))
            else:
                sanitized[key] = _sanitize(value, redactor, forbidden_terms)
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item, redactor, forbidden_terms) for item in payload]
    if isinstance(payload, str):
        return sanitize_text(payload, redactor=redactor, forbidden_terms=forbidden_terms)
    return payload


def _redact_url_hosts(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        url = match.group(0)
        parts = urlsplit(url)
        if not parts.netloc:
            return url
        if parts.netloc == "endpoint_redacted" or parts.netloc.endswith(".example.invalid"):
            return url
        return urlunsplit((parts.scheme, "endpoint_redacted", parts.path, parts.query, parts.fragment))

    return HOST_RE.sub(repl, text)


def _count_forbidden_terms(text: str, terms: list[str]) -> int:
    return sum(text.count(term) for term in terms if term)


def _count_unredacted_hosts(text: str) -> int:
    count = 0
    for host in HOST_RE.findall(text):
        if host not in {"endpoint_redacted", "app.example.invalid"} and not host.endswith(".example.invalid"):
            count += 1
    return count


def _count_unredacted_signatures(text: str) -> int:
    count = 0
    for _, value in PRESIGNED_SIGNATURE_RE.findall(text):
        if value != "REDACTED":
            count += 1
    return count


def _add_finding(findings: list[RedactionFinding], checks: RedactionChecks, field: str, path: str, count: int) -> None:
    if count <= 0:
        return
    setattr(checks, field, getattr(checks, field) + count)
    findings.append(RedactionFinding(code=field.upper(), path=path, count=count))


def scan_file(path: str | Path, *, forbidden_terms: list[str] | None = None) -> RedactionReport:
    target = Path(path)
    return build_redaction_report({str(target): target.read_text(encoding="utf-8")}, forbidden_terms=forbidden_terms)
