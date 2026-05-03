# Evidence Bundle Schema

`evidence_bundle.json` is a versioned manifest for audit, handoff, and drift workflows.

Top-level fields:

- `schema_version`: currently `rackq.evidence_bundle.v1`
- `generated_at`: UTC timestamp
- `tool`: tool name and version
- `mode`: always `REVIEW_ONLY`
- `redacted`: whether generated output identities were redacted
- `input`: policy, inventory, cluster, rack, and input hashes
- `nodes`: per-node evidence and qualification records
- `outputs`: generated output paths
- `business_impact`: review counters
- `readiness`: workload-readiness lane counts
- `coverage`: evidence-slot coverage summary
- `action_queue_counts`: review-queue priority counts
- `caveats`: review-only caveats

Per-node fields:

- `node_name`
- `evidence_dir`
- `files`
- `qualification_status`
- `confidence`
- `slurm_features`
- readiness lane can be derived from `qualification_status` and `slurm_features`
- `reason_codes`
- `blockers`
- `warnings`
- `policy_decisions`

Per-file fields:

- `kind`
- `path`
- `sha256`
- `bytes`

The bundle does not contain credentials and does not prove root cause. It records what evidence was evaluated and what review-only recommendation was produced.

Machine-readable schemas are in `schemas/`:

- `qualification_policy.schema.json`
- `node_inventory.schema.json`
- `evidence_bundle.schema.json`
- `summary.schema.json`
- `labels.schema.json`
- `quarantine.schema.json`
- `review_queue.schema.json`
