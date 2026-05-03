from __future__ import annotations

import hashlib


def stable_token(value: str, *, salt: str = "", prefix: str = "TOKEN", length: int = 12) -> str:
    payload = f"{salt}\0{value}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:length]
    return f"<{prefix}:{digest}>"
