from __future__ import annotations

import csv
import re
from pathlib import Path
from statistics import median
from typing import Iterable

from .models import NcclResult, NcclSample, PairwiseNcclRecord, PairwiseNcclResult


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text:
        return None
    text = re.sub(r"\s*(GB/s|GiB/s|gbps|GBps|ms|us|s)$", "", text, flags=re.IGNORECASE)
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    number = _parse_float(value)
    if number is None:
        return None
    return int(number)


def _percentile(values: Iterable[float], pct: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    index = round((len(ordered) - 1) * pct)
    return ordered[index]


def _metric(sample: NcclSample, use_metric: str) -> float | None:
    if use_metric == "algbw_gbps":
        return sample.algbw_gbps if sample.algbw_gbps is not None else sample.busbw_gbps
    return sample.busbw_gbps if sample.busbw_gbps is not None else sample.algbw_gbps


def _finalize_single_result(result: NcclResult, min_message_size: int, use_metric: str) -> NcclResult:
    result.wrong_count_total = sum(sample.wrong_count for sample in result.samples)
    if result.wrong_count_total > 0:
        result.correctness_error = True
        result.reason_codes.append("NCCL_WRONG_COUNT_NONZERO")
    eligible = [
        value
        for sample in result.samples
        if sample.message_size_bytes >= min_message_size
        for value in [_metric(sample, use_metric)]
        if value is not None
    ]
    if result.samples:
        result.max_message_size_bytes = max(sample.message_size_bytes for sample in result.samples)
    if eligible:
        result.best_bandwidth_gbps = max(eligible)
        result.p50_bandwidth_gbps = float(median(eligible))
        result.p10_bandwidth_gbps = _percentile(eligible, 0.10)
        result.p90_bandwidth_gbps = _percentile(eligible, 0.90)
    else:
        result.reason_codes.append("NCCL_SMALL_SAMPLE")
    if result.timeout:
        result.status = "TIMEOUT"
        result.reason_codes.append("NCCL_SINGLE_NODE_FAIL")
    elif result.correctness_error:
        result.status = "FAIL"
        result.reason_codes.append("NCCL_SINGLE_NODE_FAIL")
    elif result.parsed and eligible:
        result.status = "PASS"
        result.reason_codes.append("NCCL_SINGLE_NODE_PASS")
    elif result.present:
        result.status = "WARN"
        result.reason_codes.append("NCCL_SINGLE_NODE_WARN")
    return result


def parse_single_node_nccl(path: Path, min_message_size: int, use_metric: str = "busbw_gbps") -> NcclResult:
    result = NcclResult(present=path.exists(), reason_codes=["NCCL_SINGLE_NODE_PRESENT"] if path.exists() else ["NCCL_SINGLE_NODE_MISSING"])
    if not path.exists():
        return result
    text = path.read_text(encoding="utf-8", errors="replace")
    lower = text.lower()
    if "timeout" in lower or "timed out" in lower:
        result.timeout = True
        result.error_excerpts.append("timeout marker observed")
        result.reason_codes.append("NCCL_PAIRWISE_TIMEOUT")
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if "unhandled system error" in lowered or "invalid usage" in lowered or "failed" in lowered:
            result.correctness_error = True
            result.error_excerpts.append(stripped[:160])
            result.reason_codes.append("NCCL_CORRECTNESS_ERROR")
    first_data = next((line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")), "")
    try:
        if "," in first_data:
            result.samples = _parse_single_csv(text, result)
        else:
            result.samples = _parse_single_text(text, result)
        result.parsed = bool(result.samples)
        if not result.parsed:
            result.reason_codes.append("NCCL_PARSE_FAILED")
    except Exception as exc:  # pragma: no cover - defensive parser boundary
        result.reason_codes.append("NCCL_PARSE_FAILED")
        result.error_excerpts.append(str(exc))
    return _finalize_single_result(result, min_message_size, use_metric)


def _parse_single_csv(text: str, result: NcclResult) -> list[NcclSample]:
    rows = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    samples: list[NcclSample] = []
    reader = csv.DictReader(rows)
    for row in reader:
        size = _parse_int(row.get("message_size_bytes") or row.get("size") or row.get("bytes"))
        if size is None:
            continue
        wrong = _parse_int(row.get("wrong_count") or row.get("wrong") or row.get("#wrong")) or 0
        error_value = row.get("error") or row.get("status")
        if wrong > 0:
            result.correctness_error = True
        if error_value and str(error_value).strip().lower() == "timeout":
            result.timeout = True
        elif error_value and str(error_value).strip().lower() not in {"0", "0.0", "pass", "ok", ""}:
            result.correctness_error = True
            result.reason_codes.append("NCCL_CORRECTNESS_ERROR")
        samples.append(
            NcclSample(
                message_size_bytes=size,
                algbw_gbps=_parse_float(row.get("algbw_gbps") or row.get("algbw")),
                busbw_gbps=_parse_float(row.get("busbw_gbps") or row.get("busbw")),
                wrong_count=wrong,
                raw=dict(row),
            )
        )
    return samples


def _parse_single_text(text: str, result: NcclResult) -> list[NcclSample]:
    header: list[str] = []
    samples: list[NcclSample] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            maybe_header = stripped.lstrip("#").strip()
            lowered = maybe_header.lower()
            if "size" in lowered and ("busbw" in lowered or "algbw" in lowered):
                header = [_normalize_header(token) for token in maybe_header.split()]
            continue
        parts = stripped.split()
        if not parts or not re.match(r"^\d+$", parts[0]):
            continue
        size = _parse_int(parts[0])
        if size is None:
            continue
        row: dict[str, str] = {}
        if header:
            for index, name in enumerate(header[: len(parts)]):
                row[name] = parts[index]
        busbw = _value_from_row_or_position(row, parts, "busbw", fallback_index=-2)
        algbw = _value_from_row_or_position(row, parts, "algbw", fallback_index=-3)
        wrong = _parse_int(row.get("wrong") or row.get("#wrong") or (parts[-1] if parts else "")) or 0
        if wrong > 0:
            result.correctness_error = True
        samples.append(NcclSample(message_size_bytes=size, algbw_gbps=algbw, busbw_gbps=busbw, wrong_count=wrong, raw=row))
    return samples


def _normalize_header(token: str) -> str:
    return token.strip().lower().replace("#", "").replace("-", "_")


def _value_from_row_or_position(row: dict[str, str], parts: list[str], key: str, fallback_index: int) -> float | None:
    matches = [value for name, value in row.items() if name == key or name.endswith(key)]
    for value in reversed(matches):
        parsed = _parse_float(value)
        if parsed is not None:
            return parsed
    try:
        return _parse_float(parts[fallback_index])
    except IndexError:
        return None


def parse_pairwise_nccl_csv(path: Path, min_message_size: int, min_pairwise_busbw_gbps: float | None = None, local_node: str | None = None) -> PairwiseNcclResult:
    result = PairwiseNcclResult(present=path.exists(), reason_codes=["NCCL_PAIRWISE_PRESENT"] if path.exists() else ["NCCL_PAIRWISE_MISSING"])
    if not path.exists():
        return result
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                status = str(row.get("status") or "UNKNOWN").strip().upper()
                nodes = [node for node in str(row.get("nodes") or "").split("|") if node]
                timeout = status == "TIMEOUT" or str(row.get("timeout") or "").strip().lower() in {"1", "true", "yes"}
                wrong_count = _parse_int(row.get("wrong_count")) or 0
                result.records.append(
                    PairwiseNcclRecord(
                        test_id=str(row.get("test_id") or ""),
                        nodes=nodes,
                        gpus_per_node=_parse_int(row.get("gpus_per_node")),
                        message_size_bytes=_parse_int(row.get("message_size_bytes")),
                        busbw_gbps=_parse_float(row.get("busbw_gbps")),
                        algbw_gbps=_parse_float(row.get("algbw_gbps")),
                        duration_ms=_parse_float(row.get("duration_ms")),
                        status=status,
                        timeout=timeout,
                        wrong_count=wrong_count,
                        stderr_excerpt=row.get("stderr_excerpt") or None,
                    )
                )
        result.parsed = True
    except Exception as exc:  # pragma: no cover - defensive parser boundary
        result.warnings.append(str(exc))
        result.reason_codes.append("NCCL_PARSE_FAILED")
        return result

    eligible = [
        record.busbw_gbps
        for record in result.records
        if (record.message_size_bytes or 0) >= min_message_size and record.busbw_gbps is not None
    ]
    result.timeout_count = sum(1 for record in result.records if record.timeout)
    threshold = min_pairwise_busbw_gbps
    weak_records = []
    if threshold is not None:
        weak_records = [record for record in result.records if record.busbw_gbps is not None and record.busbw_gbps < threshold]
    weak_peers = {peer for record in weak_records for peer in record.nodes}
    if local_node:
        weak_peers.discard(local_node)
    result.weak_peer_count = len(weak_peers)
    if eligible:
        result.min_busbw_gbps = min(eligible)
        result.p50_busbw_gbps = float(median(eligible))
    if result.timeout_count:
        result.status = "TIMEOUT"
        result.reason_codes.append("NCCL_PAIRWISE_TIMEOUT")
    elif weak_records:
        result.status = "WEAK"
        result.reason_codes.append("NCCL_PAIRWISE_WEAK")
    elif result.records:
        result.status = "PASS"
        result.reason_codes.append("NCCL_PAIRWISE_PASS")
    else:
        result.status = "WARN"
        result.reason_codes.append("NCCL_SMALL_SAMPLE")
    return result
