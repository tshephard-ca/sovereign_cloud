from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ACCESS_KEY_RE = re.compile(r"\b[A-Z0-9]{16,32}\b")
ACCOUNT_ID_RE = re.compile(r"\b\d{12}\b")
ARN_RE = re.compile(r"\barn:[^\s,\"']+")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SIGNATURE_KEYS = {"x-amz-signature", "x-amz-credential", "signature", "expires", "x-amz-security-token"}


def stable_hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


class Redactor:
    def __init__(self) -> None:
        self._bucket_map: dict[str, str] = {}

    def bucket(self, name: str | None) -> str | None:
        if name is None:
            return None
        if name not in self._bucket_map:
            self._bucket_map[name] = f"bucket_{len(self._bucket_map) + 1:03d}"
        return self._bucket_map[name]


def redact_text(text: str | None) -> str | None:
    if text is None:
        return None
    value = ARN_RE.sub("arn:REDACTED", text)
    value = IP_RE.sub("ip_redacted", value)
    value = ACCOUNT_ID_RE.sub("account_redacted", value)
    value = ACCESS_KEY_RE.sub("access_key_redacted", value)
    return value


def redact_presigned_url(url: str) -> str:
    parts = urlsplit(url)
    redacted_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SIGNATURE_KEYS or "signature" in key.lower() or "credential" in key.lower():
            redacted_query.append((key, "REDACTED"))
        else:
            redacted_query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted_query), parts.fragment))
