from __future__ import annotations

from pathlib import Path
from typing import Any

from .action_queue import write_review_queue_csv
from .evidence_bundle import build_evidence_bundle, write_evidence_bundle
from .evidence_loader import load_evidence
from .impact import load_business_assumptions
from .node_inventory import load_node_inventory
from .qualification_policy import load_policy
from .redact import redact_inventory_identity, redact_results, redact_summary
from .report import build_summary, write_labels_csv, write_quarantine_csv, write_summary_json
from .rules import qualify_nodes
from .slurm_render import render_drain_review, render_slurm_fragment


def qualify_workflow(
    *,
    evidence: Path,
    node_inventory: Path | None,
    policy: Path | None,
    output_labels: Path,
    output_quarantine: Path,
    output_slurm_fragment: Path,
    output_drain_review: Path,
    summary: Path,
    evidence_bundle: Path | None = None,
    output_review_queue: Path | None = None,
    business_assumptions: Path | None = None,
    strict: bool = False,
    redact: bool = False,
    policy_loader=load_policy,
    inventory_loader=load_node_inventory,
) -> dict[str, Any]:
    qualification_policy = policy_loader(policy)
    inventory = inventory_loader(node_inventory)
    nodes = load_evidence(evidence, qualification_policy)
    original_results = qualify_nodes(nodes, qualification_policy, inventory)
    results = redact_results(original_results) if redact else original_results
    output_inventory = redact_inventory_identity(inventory) if redact else inventory
    review_queue = output_review_queue or output_labels.parent / "review_queue.csv"
    outputs = {
        "labels_csv": str(output_labels),
        "quarantine_csv": str(output_quarantine),
        "review_queue_csv": str(review_queue),
        "slurm_fragment": str(output_slurm_fragment),
        "drain_review": str(output_drain_review),
    }
    if evidence_bundle:
        outputs["evidence_bundle"] = str(evidence_bundle)
    write_labels_csv(output_labels, results)
    write_quarantine_csv(output_quarantine, results)
    write_review_queue_csv(review_queue, results)
    render_slurm_fragment(output_slurm_fragment, results)
    render_drain_review(output_drain_review, results)
    assumptions = load_business_assumptions(business_assumptions)
    summary_model = build_summary(nodes, results, output_inventory, qualification_policy.policy_id, outputs, assumptions)
    if redact:
        summary_model = redact_summary(summary_model)
    write_summary_json(summary, summary_model)
    if evidence_bundle:
        bundle = build_evidence_bundle(
            evidence,
            qualification_policy,
            inventory,
            nodes,
            original_results,
            outputs,
            policy_path=policy,
            inventory_path=node_inventory,
            redacted=redact,
        )
        write_evidence_bundle(evidence_bundle, bundle)
    return {
        "policy": qualification_policy,
        "inventory": inventory,
        "nodes": nodes,
        "results": results,
        "original_results": original_results,
        "summary": summary_model,
        "outputs": outputs,
    }
