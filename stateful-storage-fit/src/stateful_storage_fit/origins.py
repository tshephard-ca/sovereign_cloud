from __future__ import annotations


def is_generated_origin(value: str | None) -> bool:
    origin = str(value or "unknown").lower()
    return origin in {"synthetic", "generated", "sample", "example", "simulated"} or origin.startswith(
        ("synthetic_", "generated_", "sample_", "example_", "simulated_")
    )
