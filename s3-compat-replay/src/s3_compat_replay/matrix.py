from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .models import CompatibilityMatrix, MatrixTargetSummary, ProbeResults, UsageProfile
from .report import build_summary, collect_mismatches, read_json


def build_matrix(profile_path: str | Path, result_paths: list[str | Path]) -> CompatibilityMatrix:
    profile = UsageProfile(**read_json(profile_path))
    targets: list[MatrixTargetSummary] = []
    all_questions: list[str] = []
    for result_path in result_paths:
        path = Path(result_path)
        results = ProbeResults(**read_json(path))
        summary = build_summary(profile, results)
        mismatches = collect_mismatches(results)
        code_counts = Counter(mismatch.mismatch_code for mismatch in mismatches)
        for question in summary.recommended_next_questions:
            if question not in all_questions:
                all_questions.append(question)
        targets.append(
            MatrixTargetSummary(
                target_id=path.stem,
                compatibility_status=summary.compatibility_status,
                probes_run=results.probes_run,
                probes_failed=results.probes_failed,
                probes_skipped=results.probes_skipped,
                blocker_count=summary.mismatch_counts.get("BLOCKER", 0),
                review_count=summary.mismatch_counts.get("REVIEW", 0),
                info_count=summary.mismatch_counts.get("INFO", 0),
                top_codes=[code for code, _ in code_counts.most_common(5)],
            )
        )
    return CompatibilityMatrix(generated_at=_now(), target_count=len(targets), targets=targets, recommended_questions=all_questions[:20])


def matrix_markdown(matrix: CompatibilityMatrix) -> str:
    lines = ["# Compatibility Matrix", "", "| Target | Status | Run | Failed | Skipped | Blockers | Review | Top Codes |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for target in matrix.targets:
        lines.append(
            f"| {target.target_id} | {target.compatibility_status} | {target.probes_run} | {target.probes_failed} | {target.probes_skipped} | {target.blocker_count} | {target.review_count} | {', '.join(target.top_codes)} |"
        )
    lines.extend(["", "## Recommended Questions", ""])
    if matrix.recommended_questions:
        lines.extend(f"- {question}" for question in matrix.recommended_questions)
    else:
        lines.append("- No target-specific questions were generated.")
    lines.extend(["", "This matrix compares probe results. It does not rank vendors automatically.", ""])
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
