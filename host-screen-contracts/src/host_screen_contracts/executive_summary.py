from __future__ import annotations

from typing import Any


def render_executive_summary(
    *,
    package_id: str,
    transaction_id: str,
    readiness: dict[str, Any],
    realism: dict[str, Any],
    extraction: dict[str, Any],
    privacy: dict[str, Any],
    validation: dict[str, Any],
    benchmark: dict[str, Any],
) -> str:
    status = readiness["review_package_status"]
    lines = [
        f"# Review Package: {package_id}",
        "",
        f"Transaction: `{transaction_id}`",
        f"Review package status: `{status}`",
        "",
        "## Business Use",
        "",
        "This package turns recorded host-screen behavior into a reviewable API/wrapper contract candidate with replay, privacy, drift, and readiness evidence. It is a planning and handoff artifact, not live host automation.",
        "",
        "## Decision Snapshot",
        "",
        f"- Canonical cases: {extraction.get('canonical_case_count', 0)}",
        f"- Drift evidence cases: {extraction.get('drift_case_count', 0)}",
        f"- Non-contract cases: {extraction.get('non_contract_case_count', 0)}",
        f"- Contract-ready rate: {benchmark.get('contract_ready_rate', 0):.2f}",
        f"- Field-map coverage: {benchmark.get('field_map_coverage', 0):.2f}",
        f"- Business-impact score: {realism.get('business_impact_score', 0)}",
        f"- Unredacted privacy findings: {privacy.get('unredacted_sensitive_value_count', 0)}",
        "",
        "## Primary Artifacts",
        "",
        f"- Canonical contract: `{extraction.get('canonical_contract')}`",
        f"- API candidate: `{extraction.get('api_candidate')}`",
        f"- Replay test: `{extraction.get('combined_replay_test')}`",
        f"- Drift evidence: `{extraction.get('drift_evidence')}`",
        f"- Flow graph: `{extraction.get('flow_graph')}`",
        "",
    ]
    if readiness.get("blockers"):
        lines.extend(["## Blockers", ""])
        lines.extend(f"- `{item}`" for item in readiness["blockers"])
        lines.append("")
    if readiness.get("review_items"):
        lines.extend(["## Review Items", ""])
        lines.extend(f"- `{item}`" for item in readiness["review_items"])
        lines.append("")
    lines.extend(["## Recommended Next Actions", ""])
    lines.extend(f"- `{item}`" for item in readiness.get("recommended_next_actions", []))
    lines.extend(
        [
            "",
            "## Evidence Boundaries",
            "",
            f"- Evidence kind: `{realism.get('evidence_kind')}`",
            f"- Actual maturity level: `{realism.get('actual_maturity_level') or realism.get('maturity_level')}`",
            f"- Simulates maturity level: `{realism.get('simulates_maturity_level')}`",
            f"- Synthetic evidence: `{realism.get('synthetic')}`",
            "- Replay validates recorded traces only.",
            "- The OpenAPI file is a contract candidate, not a deployed API.",
            "- Field names inferred without field-map review are not authoritative.",
        ]
    )
    if validation.get("warnings"):
        lines.extend(["", "## Validation Warnings", ""])
        lines.extend(f"- `{warning}`" for warning in validation["warnings"])
    return "\n".join(lines) + "\n"
