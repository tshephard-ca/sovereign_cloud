# Demo: Recovery Preflight Assessment

This demo uses only synthetic local files. It does not connect to hosts, DNS servers, backup systems, or directory services.

## Static Example

Run the packaged example:

```bash
dr-prereq-lint analyze-package \
  --package examples/preflight_package.yml \
  --output-dir out/demo-static
```

The static example declares `dr-test-001` as the application recovery set. DNS evidence from protected application systems references shared resolver, identity, database, and file prerequisites that are not declared in that recovery set. The expected result is a preflight `FAIL` because core prerequisite services are outside the declared recovery scope.

Review the primary artifact first:

```bash
cat out/demo-static/preflight_assessment.json
```

Then route owner work:

```bash
cat out/demo-static/owner_worklist.csv
```

The report is meant for a recovery-scope review:

```bash
cat out/demo-static/preflight_report.md
```

## Generated Realistic Scenario

Create a deterministic scenario where the application recovery set omits a database host:

```bash
dr-prereq-lint generate-sample-data \
  --scenario missing-database-host \
  --output-dir out/sample-missing-database
```

Run the package workflow over the generated package:

```bash
dr-prereq-lint analyze-package \
  --package out/sample-missing-database/preflight_package.yml \
  --output-dir out/sample-missing-database/run
```

This scenario should produce a `FAIL` decision with a `data_services` gap for the core database service. The owner worklist should route that item to the database owner with strong evidence from repeated protected-system DNS lookups.

Key files:

- `preflight_assessment.json`: decision, business impact, service-family status, limitations, evidence improvement actions.
- `owner_worklist.csv`: rows grouped by accountable owner team.
- `coverage_gaps.csv`: audit details with reason codes.
- `evidence_detail.csv`: observed prerequisites with match basis and confidence.
- `preflight_report.md`: readable review document.
- `preflight_evidence_bundle.zip`: shareable bundle with fingerprints.

## What To Look For

Open `preflight_assessment.json` and find:

- `decision`: the overall preflight status.
- `business_impact`: the concise explanation for the recovery review.
- `service_families`: grouped prerequisite coverage such as `data_services`, `identity_platform`, and `name_resolution`.
- `owner_work_items`: work that can be assigned before a recovery test.
- `evidence_improvement_actions`: concrete input improvements when evidence is weak or partial.
- `limitations`: scope and honesty caveats that should stay attached to any shared result.

Open `owner_worklist.csv` and sort by `owner_team`, `impact`, and `severity`. This is the handoff file for deciding whether a prerequisite belongs in the recovery set, should start first, is provided by another recovery process, or is an accepted risk.

## Business Throughline

The value is not that the tool proves recovery readiness. It does not.

The value is that it turns noisy recovery evidence into a compact review package:

- what appears missing,
- which service family it belongs to,
- who should answer,
- what evidence supports the finding,
- what evidence is still weak,
- and which caveats must be kept with the result.

That is enough to improve recovery-test scoping before teams spend time booting systems and discovering basic prerequisites late.
