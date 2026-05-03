"""Normalization helpers used by parsers, matching, and reports."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import ipaddress
import re
from typing import Iterable


MULTI_VALUE_RE = re.compile(r"[,;|]+")
MULTI_VALUE_WITH_SPACE_RE = re.compile(r"[,;|\s]+")


def clean_text(value: object | None) -> str:
    return str(value or "").strip()


def normalize_fqdn(value: object | None) -> str:
    text = clean_text(value).lower().rstrip(".")
    return re.sub(r"\s+", "", text)


def short_name(value: object | None) -> str:
    fqdn = normalize_fqdn(value)
    return fqdn.split(".", 1)[0] if fqdn else ""


def split_multi(value: object | None, *, whitespace: bool = False) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    splitter = MULTI_VALUE_WITH_SPACE_RE if whitespace else MULTI_VALUE_RE
    return [part.strip() for part in splitter.split(text) if part.strip()]


def normalize_ip(value: object | None) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return ""


def normalize_ip_list(value: object | None) -> list[str]:
    ips: list[str] = []
    for part in split_multi(value):
        ip = normalize_ip(part)
        if ip and ip not in ips:
            ips.append(ip)
    return ips


def normalize_fqdn_list(value: object | None, *, whitespace: bool = False) -> list[str]:
    names: list[str] = []
    for part in split_multi(value, whitespace=whitespace):
        name = normalize_fqdn(part)
        if name and name not in names:
            names.append(name)
    return names


def parse_bool(value: object | None) -> bool | None:
    text = clean_text(value).lower()
    if text == "":
        return None
    if text in {"1", "true", "t", "yes", "y", "included", "include", "selected", "recover"}:
        return True
    if text in {"0", "false", "f", "no", "n", "excluded", "exclude", "not_selected", "skip"}:
        return False
    return None


def parse_timestamp(value: object | None) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_text)
        return _with_utc(parsed)
    except ValueError:
        pass
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%d%H%M%S",
    )
    for fmt in formats:
        try:
            return _with_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def _with_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_private_or_internal_ip(value: object | None) -> bool:
    ip_text = normalize_ip(value)
    if not ip_text:
        return False
    ip = ipaddress.ip_address(ip_text)
    return ip.is_private or ip.is_loopback or ip.is_link_local


def infer_internal_domains(fqdns: Iterable[str]) -> list[str]:
    domains: set[str] = set()
    for fqdn in fqdns:
        labels = [label for label in normalize_fqdn(fqdn).split(".") if label]
        if len(labels) < 3:
            continue
        for idx in range(1, len(labels) - 1):
            suffix = ".".join(labels[idx:])
            if "." in suffix:
                domains.add(suffix)
    return sorted(domains)


def qname_in_domains(qname: str, domains: Iterable[str]) -> bool:
    name = normalize_fqdn(qname)
    for domain in domains:
        clean_domain = normalize_fqdn(domain)
        if name == clean_domain or name.endswith("." + clean_domain):
            return True
    return False


def stable_hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def compact_join(values: Iterable[str], *, limit: int | None = None) -> str:
    seen: list[str] = []
    for value in values:
        text = clean_text(value)
        if text and text not in seen:
            seen.append(text)
        if limit is not None and len(seen) >= limit:
            break
    return "|".join(seen)
