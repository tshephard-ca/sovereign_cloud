from __future__ import annotations

from pathlib import Path
from typing import Any

from .review_package import build_review_package


def run_review_pipeline(
    package_dir: str | Path,
    *,
    output_dir: str | Path,
    strict: bool = False,
) -> dict[str, Any]:
    return build_review_package(package_dir, output_dir=output_dir, strict=strict)
