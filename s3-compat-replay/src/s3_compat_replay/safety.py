from __future__ import annotations


UNSAFE_PREFIXES = {"", "/", "*", ".", "./", "/*"}


def validate_scratch_prefix(prefix: str, min_length: int = 8) -> list[str]:
    errors: list[str] = []
    if prefix in UNSAFE_PREFIXES:
        errors.append("scratch prefix is empty or too broad")
    if len(prefix) < min_length:
        errors.append(f"scratch prefix must be at least {min_length} characters")
    if not prefix.endswith("/"):
        errors.append("scratch prefix must end with '/'")
    if prefix.startswith("/") or ".." in prefix.split("/"):
        errors.append("scratch prefix must be a relative object-key prefix")
    if prefix.count("/") == 0:
        errors.append("scratch prefix must contain a delimiter")
    return errors


def ensure_key_within_prefix(key: str, prefix: str) -> None:
    if not key.startswith(prefix):
        raise ValueError("SCRATCH_PREFIX_SAFETY_FAILED: key is outside scratch prefix")


def probe_needs_write(probe: object) -> bool:
    setup = getattr(probe, "setup", [])
    steps = getattr(probe, "steps", [])
    write_ops = {
        "PutObject",
        "CopyObject",
        "DeleteObject",
        "DeleteObjects",
        "PutObjectTagging",
        "DeleteObjectTagging",
        "PutObjectAcl",
        "CreateMultipartUpload",
        "UploadPart",
        "UploadPartCopy",
        "CompleteMultipartUpload",
        "AbortMultipartUpload",
        "PutObjectRetention",
        "PutObjectLegalHold",
    }
    return any(getattr(step, "operation", None) in write_ops for step in [*setup, *steps])
