from __future__ import annotations

import csv
from pathlib import Path

from .models import BenchmarkSample


SAMPLE_COLUMNS = [
    "endpoint_id",
    "prompt_id",
    "measured",
    "status",
    "http_status",
    "started_at",
    "end_to_end_latency_ms",
    "time_to_first_token_ms",
    "inter_token_latency_p50_ms",
    "inter_token_latency_p95_ms",
    "input_tokens",
    "output_tokens",
    "token_count_source",
    "output_tokens_per_second",
    "response_mode",
    "error_code",
    "error_text_redacted",
    "warnings",
]


def write_samples_csv(samples: list[BenchmarkSample], path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_COLUMNS)
        writer.writeheader()
        for sample in samples:
            row = sample.model_dump(mode="json")
            row["warnings"] = ";".join(sample.warnings)
            writer.writerow({column: row.get(column) for column in SAMPLE_COLUMNS})
