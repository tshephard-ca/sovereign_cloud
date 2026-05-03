from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import ensure_parent


def build_portfolio(summary_path: Path, labels_path: Path, quarantine_path: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    labels = _read_csv(labels_path)
    quarantine = _read_csv(quarantine_path)
    reason_counter: Counter[str] = Counter()
    blocker_counter: Counter[str] = Counter()
    warning_counter: Counter[str] = Counter()
    confidence_counter: Counter[str] = Counter()
    for row in labels:
        confidence_counter[row["confidence"]] += 1
        reason_counter.update(_split_codes(row.get("reason_codes", "")))
        blocker_counter.update(_split_codes(row.get("blockers", "")))
        warning_counter.update(_split_codes(row.get("warnings", "")))
    return {
        "mode": "REVIEW_ONLY",
        "cluster_id": summary.get("cluster_id"),
        "rack_id": summary.get("rack_id"),
        "generated_at": summary.get("generated_at"),
        "qualification": summary.get("qualification", {}),
        "labels": summary.get("labels", {}),
        "business_impact": summary.get("business_impact", {}),
        "readiness": summary.get("readiness", {}),
        "coverage": summary.get("coverage", {}),
        "action_queue_counts": summary.get("action_queue_counts", {}),
        "confidence": dict(sorted(confidence_counter.items())),
        "top_reason_codes": reason_counter.most_common(15),
        "top_blockers": blocker_counter.most_common(15),
        "top_warnings": warning_counter.most_common(15),
        "operator_questions": summary.get("top_operator_questions", []),
        "review_nodes": [
            {
                "node_name": row["node_name"],
                "recommendation": row["recommendation"],
                "primary_reason": row["primary_reason"],
                "operator_action": row["operator_action"],
            }
            for row in quarantine
            if row["recommendation"] != "NONE"
        ],
    }


def write_portfolio_json(path: Path, portfolio: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(portfolio, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_portfolio_markdown(path: Path, portfolio: dict[str, Any]) -> None:
    ensure_parent(path)
    impact = portfolio.get("business_impact", {})
    lines = [
        "# Rack Qualification Portfolio",
        "",
        "This is a review-only portfolio of qualification evidence, workload-readiness lanes, and scheduler-facing labels.",
        "",
        "## Capacity At Risk",
        "",
    ]
    for key in sorted(impact):
        lines.append(f"- {key}: {impact[key]}")
    lines.extend(["", "## Workload Readiness", ""])
    for key, value in portfolio.get("readiness", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Evidence Coverage", ""])
    for key, value in portfolio.get("coverage", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Qualification Counts", ""])
    for key, value in portfolio.get("qualification", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Top Blockers", ""])
    for code, count in portfolio.get("top_blockers", []):
        lines.append(f"- {code}: {count}")
    lines.extend(["", "## Top Warnings", ""])
    for code, count in portfolio.get("top_warnings", []):
        lines.append(f"- {code}: {count}")
    lines.extend(["", "## Review Nodes", ""])
    for node in portfolio.get("review_nodes", []):
        lines.append(f"- {node['node_name']}: {node['recommendation']} because `{node['primary_reason']}`")
    lines.extend(["", "## Operator Questions", ""])
    for question in portfolio.get("operator_questions", []):
        lines.append(f"- {question}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _split_codes(value: str) -> list[str]:
    return [code for code in value.split(";") if code]
