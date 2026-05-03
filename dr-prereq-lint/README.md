# dr-prereq-lint

`dr-prereq-lint` builds a local **Recovery Preflight Assessment** from a backup inventory and normalized DNS query evidence.

It answers one operational question:

```text
Do protected systems appear to reference prerequisite services that are absent from the declared recovery set?
```

The business value is practical: before a recovery test burns time on application validation, teams can see whether name resolution, identity, database, file, license, remote-access, time, or other prerequisite services are missing from the declared scope. The output is designed for review and owner routing, not for orchestration.

## What It Does

- Reads a CSV backup inventory and a normalized CSV DNS query log.
- Uses optional prerequisite catalog, required resolver, owner map, accepted risk, recovery-set, and policy files.
- Produces `preflight_assessment.json`, `owner_worklist.csv`, `preflight_report.md`, audit CSVs, `summary.json`, and an evidence bundle.
- Groups gaps by business-facing service family and routes work items to owner teams.
- Runs fully offline and deterministically.

## What It Does Not Do

It does not verify backups, boot systems, orchestrate recovery, connect to DNS servers, scan networks, query directory services, call backup APIs, parse raw DNS logs in the core path, build a CMDB, or prove disaster-recovery readiness.

It never performs live DNS queries, directory-service binds, ping, port scans, packet capture, credential use, or external service calls.

## Quickstart

Install from the repository root:

```bash
python -m pip install -e .
```

Run the full package workflow:

```bash
dr-prereq-lint analyze-package \
  --package examples/preflight_package.yml \
  --output-dir out/preflight
```

Primary outputs:

- `out/preflight/preflight_assessment.json`: business-facing decision, service-family gaps, owner work items, evidence quality, caveats.
- `out/preflight/owner_worklist.csv`: actionable owner-routed rows.
- `out/preflight/preflight_report.md`: readable assessment for a recovery-test review.
- `out/preflight/coverage_gaps.csv`: detailed audit findings.
- `out/preflight/evidence_detail.csv`: normalized observed prerequisite evidence.
- `out/preflight/preflight_evidence_bundle.zip`: shareable bundle with fingerprints and generated artifacts.

The legacy explicit command still works, with clearer aliases:

```bash
dr-prereq-lint analyze \
  --backup-inventory examples/backup_inventory.csv \
  --dns-log examples/dns_queries.csv \
  --recovery-set dr-test-001 \
  --prerequisite-catalog examples/prerequisite_catalog.yml \
  --required-resolvers examples/required_resolvers.yml \
  --policy examples/policy.yml \
  --owner-map examples/owner_map.csv \
  --output-coverage-gaps out/coverage_gaps.csv \
  --output-evidence-detail out/evidence_detail.csv \
  --summary out/summary.json \
  --output-assessment out/preflight_assessment.json \
  --output-owner-worklist out/owner_worklist.csv
```

Old names remain supported: `--known-prereqs`, `--resolver-hints`, `--config`, `--output-findings`, and `--output-observed`.

## Input Package

A preflight package is a small manifest that keeps inputs and policy together:

```yaml
schema_version: "1.0"
recovery_set: dr-test-001

inputs:
  backup_inventory: backup_inventory.csv
  dns_queries: dns_queries.csv
  prerequisite_catalog: prerequisite_catalog.yml
  required_resolvers: required_resolvers.yml
  answer_map: answer_map.csv
  accepted_risks: accepted_risks.yml
  recovery_sets: recovery_sets.yml
  owner_map: owner_map.csv
  policy: policy.yml

policy:
  pack: isolated_recovery_lab
  window_hours: 24
  compare_window_hours: [24, 168]
  include_unmapped_clients: true
  include_external: false
```

`known_prereqs.yml`, `resolver_hints.yml`, and `thresholds.yml` are still accepted for compatibility. The clearer names are:

- `prerequisite_catalog.yml`: prerequisite categories, internal domains, deterministic name/regex rules.
- `required_resolvers.yml`: resolvers that must be available to the recovery set.
- `policy.yml`: thresholds, severities, windowing, and inclusion defaults.

## Core Inputs

`backup_inventory.csv` should include at least a workload name. For useful business output, include FQDNs, IPs, recovery-set inclusion, role tags, owner team, business service, criticality, recovery tier, environment, and site.

`dns_queries.csv` is normalized DNS query evidence. Required fields are `qname` plus `client_ip` or `client_name`; strongly preferred fields are timestamp, qtype, rcode, answer names, answer IPs, resolver name, and resolver IP.

DNS logs show lookup behavior only. They are useful because many recovery failures are prerequisite and ordering failures, but they are not proof of successful application traffic.

## Reading The Assessment

`PASS` means no required prerequisite gap was found in the supplied evidence.

`REVIEW` means evidence is weak, incomplete, accepted-risk based, or needs owner confirmation.

`FAIL` means at least one critical prerequisite appears absent from the declared recovery set.

None of these statuses proves that a recovery test will pass. The assessment is a review artifact for scoping, sequencing, and owner follow-up.

## Generate Realistic Local Data

Create a deterministic sample scenario:

```bash
dr-prereq-lint generate-sample-data \
  --scenario missing-database-host \
  --output-dir out/sample-missing-database
```

Create a larger benchmark:

```bash
dr-prereq-lint generate-benchmark-data \
  --protected-systems 500 \
  --queries 100000 \
  --missing-prereq-rate 0.15 \
  --seed 7 \
  --output-dir out/benchmark-500
```

The generator creates owner context, business service fields, malformed-input cases, multiple DNS profiles, optional answer maps, accepted risks, recovery-set metadata, expected summaries, expected preflight assessments, and owner worklists.

## Human Outputs

Create a report from audit files:

```bash
dr-prereq-lint report \
  --findings out/coverage_gaps.csv \
  --summary out/summary.json \
  --owner-map examples/owner_map.csv \
  --output out/preflight_report.md
```

Create owner questions:

```bash
dr-prereq-lint generate-questions \
  --findings out/coverage_gaps.csv \
  --owner-map examples/owner_map.csv \
  --output out/handoff_questions.md
```

Create a checklist:

```bash
dr-prereq-lint checklist \
  --observed out/evidence_detail.csv \
  --owner-map examples/owner_map.csv \
  --output out/recovery_prereq_checklist.csv
```

## Architecture

- `pipeline.py`: primary analysis entry point; `lint_rules.py` remains as a compatibility facade for older imports.
- `classify_queries.py` and `classify_prereqs.py`: deterministic DNS evidence classification and aggregation.
- `coverage.py`, `candidates.py`, `decision.py`, and `evidence.py`: decision status, service families, identities, owner work items, and evidence improvement actions.
- `assessment.py`: builds the business-facing Recovery Preflight Assessment.
- `preflight_package.py`: loads package manifests and resolves relative paths.
- `report.py` and `human_reports.py`: machine-readable writers, owner worklist, Markdown report, questions, checklist, and bundle.
- `generate_data.py`: deterministic sample and benchmark input generation.

## Privacy And Security

- Local-only execution.
- No telemetry.
- No network calls.
- No credentials.
- No DNS queries.
- No directory-service binds.
- No backup API calls.
- Traces, DNS logs, and inventories may contain sensitive hostnames, IPs, owner names, and internal domains.
- Use `--redact` before sharing outputs outside the authorized recovery team.

## Proprietary And Platform Boundary

- The core does not bundle, invoke, link, or redistribute backup, DNS, directory-service, or recovery-orchestration tools.
- The core consumes normalized CSV/YAML input packages.
- Users are responsible for having rights to export, inspect, and use their own recovery evidence.
- Source-specific parsers or live integrations should remain optional adapters with their own licensing and support boundaries.

## Data Honesty Caveats

- DNS logs show lookups, not actual connections.
- DNS caching can hide dependencies.
- A 24-hour window can miss weekly, monthly, startup-only, or failover-only dependencies.
- If answer data is absent, target identity may be unknown.
- SRV records may show service discovery, not the exact server ultimately used.
- Inventory absence means absent from the supplied CSV, not absent from every backup platform.
- Keyword and regex classification are review signals, not proof.
- External destinations are ignored by default unless configured.
- This tool does not replace recovery testing.

## More Documentation

- `docs/demo.md`: end-to-end demo and output interpretation.
- `docs/reason_codes.md`: warning, finding, and missing-data reason-code dictionary.

## Roadmap

1. Raw DNS log adapters as optional packages outside the core.
2. Backup-inventory mappers for common export shapes without adding backup API clients.
3. Drift comparison between preflight packages across test cycles.
4. Recovery-scope portfolio mode for many declared recovery sets.
5. Richer error and accepted-risk workflows with expiry reporting.
6. Optional network-flow correlation as a separate module.
7. HTML report generation from the same assessment JSON.
8. Adapter contract for approved customer evidence exporters.
