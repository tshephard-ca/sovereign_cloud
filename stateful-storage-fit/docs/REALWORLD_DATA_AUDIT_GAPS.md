# Real-World Data Generation Audit Gaps

Audit date: 2026-04-30

Audit artifacts:

- `out/realworld-full-coverage-audit/bundle/`
- `out/realworld-full-coverage-audit/bundle-validation.json`
- `out/realworld-full-coverage-audit/input-realism.json`
- `out/realworld-full-coverage-audit/fit.json`
- `out/realworld-full-coverage-audit/decision-validation.json`
- `out/realworld-full-coverage-audit/profile-snapshot.json`
- `out/realworld-full-coverage-audit/corpus/realworld-full-coverage-audit.yml`
- `out/realworld-full-coverage-audit/case-validation.json`
- `out/realworld-full-coverage-audit/corpus-summary.json`
- `out/realworld-full-coverage-audit/corpus-coverage.json`
- `out/realworld-full-coverage-audit/corpus-eval.json`

## What Was Run

The local collector was run with first-pass redaction and balanced process redaction. Scoped `du` evidence was generated for a user-declared path. The resulting bundle was checked against the example storage profile, then validated with bundle, input-realism, decision, profile-snapshot, case, corpus-summary, corpus-coverage, and corpus-evaluation workflows.

Unit tests also passed:

```text
46 passed
```

## Audit Result

The tooling can generate a coherent local evidence bundle and a valid storage-fit decision record. It cannot yet generate full-coverage real-world calibration data, and it cannot prove business impact without human review, outcome records, and business-impact records.

Observed generated-input quality:

- Bundle valid: `true`
- Core completeness score: `1.0`
- Topology completeness score: `0.429`
- Application evidence score: `0.5`
- Redaction preservation score: `1.0`
- Overall bundle quality score: `0.811`
- Input-realism valid: `true`
- Input-realism warnings:
  - `DECLARED_APP_PATH_NOT_OBSERVED_IN_MOUNT_OUTPUT`
  - `PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC`
  - `TOPOLOGY_EVIDENCE_LOW`

Observed generated-output quality:

- Decision validation valid: `true`
- Fit status: `REVIEW`
- Recommended storage class: `fast-rwo`
- Confidence: `MEDIUM`
- Capacity risk: `MEDIUM`
- Latency risk: `LOW`
- Missing data:
  - `iostat_device_mapping`
- Decision warnings:
  - `NETWORK_FILESYSTEM_ON_NON_DATA_MOUNT`
  - `IOSTAT_DEVICE_MAPPING_UNCERTAIN`
  - `TOPOLOGY_EVIDENCE_LOW`
  - `DECLARED_APP_PATH_NOT_OBSERVED_IN_MOUNT_OUTPUT`
- Case validation valid: `true`
- Trusted label: `false`
- Calibration ready: `false`
- Review quality score: `0.0`
- Outcome quality score: `0.0`
- Business impact quality score: `0.0`

Observed corpus readiness:

- Example corpus case count: `3`
- Trusted label count: `0`
- Outcome-linked case count: `0`
- Decision accuracy on synthetic labels: `1.0`
- Readiness level: `RESEARCH_ONLY`
- Readiness blockers:
  - `INSUFFICIENT_OUTCOME_LINKED_CASES`
  - `INSUFFICIENT_OUTCOME_COVERAGE`
  - `INSUFFICIENT_TRUSTED_LABEL_COVERAGE`

## Extensive Gap List

### Input Data Generation Gaps

1. Topology data is incomplete on normal hosts.
   - `blkid`, `pvs`, `vgs`, and `lvs` produced empty or failed outputs in the run.
   - Current behavior records this honestly, but full coverage needs a strategy for hosts without LVM tools or privileged block metadata access.

2. Topology completeness is below a full-coverage threshold.
   - Observed topology score was `0.429`.
   - This is enough for a cautious review result, not enough for high-confidence lineage inference.

3. The generator does not create a matching path-purpose file from observed mounts.
   - The sample path-purpose file declares `/data`.
   - The collected local evidence did not observe `/data`, so validation warned with `DECLARED_APP_PATH_NOT_OBSERVED_IN_MOUNT_OUTPUT`.

4. Path-purpose evidence is still manually supplied.
   - The collector cannot infer ownership of `/data`, `/srv`, `/var/lib/...`, or other paths.
   - This is correct from a data-honesty perspective, but it means full coverage requires an owner questionnaire or an explicit path-purpose generator template.

5. Process evidence is shallow after safe redaction.
   - Balanced redaction preserves executable names and some flags, but it does not prove application topology, writers, clustering, or dependency boundaries.

6. Process family coverage depends on what is running at collection time.
   - A short process list from one VM may miss batch jobs, inactive services, timer-triggered jobs, maintenance tasks, and failover-only processes.

7. Short iostat samples remain weak evidence.
   - The generator captures `iostat -x -d -m 1 5`.
   - This is not a benchmark and cannot characterize peak, backup, maintenance, or incident-period storage behavior.

8. Device mapping is not reliable enough.
   - The output carried `IOSTAT_DEVICE_MAPPING_UNCERTAIN`.
   - Full coverage needs stronger mapping from mount source to physical/logical iostat device, especially for mapper, mdraid, LVM, multipath, encrypted, and virtual disks.

9. Network filesystem context is underexplained.
   - The decision warned about network storage on a non-data mount.
   - The tool detects the signal but cannot determine whether it is session, system, artifact, backup, shared content, or application-critical storage.

10. `du` coverage is path-scoped but not workload-scoped.
    - `collect-du` only measures user-provided paths.
    - It does not know whether those paths are complete, duplicated, stale, cache-only, or application-owned.

11. Redacted `du` evidence cannot be automatically reconciled to unredacted path-purpose files.
    - Redaction preserves shape, but a declared unredacted path can mismatch a redacted bundle unless the workflow captures a safe owner mapping.

12. The storage profile used in the audit is generic.
    - Input realism correctly flagged `PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC`.
    - Full business use requires real target storage options supplied by the platform owner.

13. Profile provenance is descriptive, not authoritative.
    - The profile snapshot records checksum and metadata.
    - It does not prove the profile matches the current target platform because the tool intentionally does not inspect clusters.

14. No schema-backed path-purpose quality score exists.
    - Path-purpose records are parsed, but there is no score for owner identity, approval, staleness, confidence, or coverage against observed mounts.

15. No workload-time-window metadata is collected.
    - The bundle does not say whether collection occurred during idle, business hours, backup, batch window, peak, or outage.

16. No data-change-rate evidence is generated.
    - Capacity request is based on current used space plus heuristic headroom.
    - There is no historical growth, churn, retention, compaction, archive, or purge behavior.

17. No file-count and file-size distribution evidence beyond inode summary.
    - Inode pressure is sampled, but the tool does not know small-file distributions, directory fanout, or metadata-heavy workloads.

18. No write-safety or consistency evidence is generated.
    - The inputs do not show fsync behavior, write ordering assumptions, lock semantics, or crash-recovery requirements.

19. No ownership boundary between application data and system data is proven.
    - A non-system large mount can be a real application mount, a user home, a cache, build output, backup staging, or unrelated shared data.

20. No multi-VM relationship data is generated.
    - The core question is one VM, but RWX and shared namespace requirements often depend on multiple VMs or active/passive topology.

### Output Realism Gaps

21. A valid decision can still be only `REVIEW`.
    - The generated output is internally consistent and validator-clean, but it has warnings and missing data that prevent high-confidence use.

22. The decision does not prove storage performance sufficiency.
    - It reports latency risk and recommends deeper testing when needed.
    - It cannot say a target environment will satisfy the workload under load.

23. Capacity risk remains heuristic.
    - The request uses current used GiB plus configured headroom.
    - It does not know growth rate, retention policy, cleanup, compression, dedupe, or expected onboarding size.

24. Matched storage class ranking is based on supplied profile semantics only.
    - It can rank `fast-rwo` over other generic classes in the sample profile.
    - It cannot validate actual backend limits, quotas, topology, noisy-neighbor behavior, expansion operations, or snapshot behavior.

25. Redacted output is readable but loses some operational specificity.
    - Redacted mount paths preserve shape but not business meaning.
    - That is appropriate for privacy, but follow-up review still needs an owner-held mapping.

26. Evidence questions are not yet a closed-loop workflow.
    - REVIEW cases can include missing evidence questions, but the tool does not yet convert answers into a tracked follow-up evidence bundle.

27. The validator checks consistency, not truth.
    - `validate-decision` can catch malformed or unsupported outputs.
    - It cannot confirm that the user-supplied text inputs are complete or truthful.

28. The output does not quantify uncertainty probabilistically.
    - Confidence is categorical.
    - There are no calibrated likelihoods for false PASS, false FAIL, or review escalation.

29. The output does not separate reversible and irreversible blockers.
    - A missing RWX class, insufficient size, and raw block requirement are hard blockers for the supplied profile.
    - The business severity depends on whether platform owners can add a class, change architecture, or split data.

30. No persona-specific output exists for platform, application owner, storage engineering, and business owner.
    - The JSON is useful as a machine-readable artifact.
    - Business impact requires tailored summaries and decision records, not just fit JSON.

### Coverage Dataset Gaps

31. Example corpus is synthetic and small.
    - Current example corpus has `3` cases.
    - It is useful for regression, not empirical defensibility.

32. Trusted label count is zero.
    - Corpus evaluation reported `trusted_label_count: 0`.
    - There is no expert consensus or adjudication evidence in the example corpus.

33. Outcome-linked case count is zero.
    - Corpus evaluation reported `outcome_linked_case_count: 0`.
    - There is no real evidence that decisions predicted later storage outcomes.

34. Corpus readiness remains `RESEARCH_ONLY`.
    - Blockers are insufficient outcome-linked cases, insufficient outcome coverage, and insufficient trusted label coverage.

35. Full family coverage is missing.
    - Coverage gaps remain for relational database, shared filesystem, file server, search/logging, queue/streaming, and generic stateful app families.

36. Reason-code coverage is missing.
    - Coverage gaps remain for high capacity risk, high latency risk, raw block hints, and shared filesystem detection.

37. Capability coverage is too narrow.
    - The existing examples do not build a broad empirical distribution across RWO, RWX, Block, file storage, local storage, capacity overflow, expansion, and snapshot needs.

38. No negative-control cases exist.
    - The corpus needs cases where the tool should not infer database, shared filesystem, raw block, or high latency despite noisy signals.

39. No borderline cases exist.
    - The corpus needs near-threshold capacity, latency, utilization, and queue-depth cases to test rule stability.

40. No malformed-but-common input corpus exists.
    - Real inputs often have truncated columns, localized command output, missing headers, unusual df units, wrapped process args, containerized mount paths, and partial command failures.

41. No temporal repeat corpus exists.
    - The same workload collected at different times is needed to test decision stability and drift.

42. No cross-reviewer disagreement corpus exists.
    - The adjudication path exists, but the corpus does not exercise disagreement patterns at scale.

43. No outcome-lag handling exists.
    - Real outcomes may arrive weeks later.
    - The workflow tracks missing outcomes, but does not manage due dates, reminders, aging, or stale cases.

44. No profile drift corpus exists.
    - Storage profiles can change.
    - The corpus does not test whether an old decision is invalidated by a profile change.

45. No policy-pack calibration depth exists.
    - Policy packs exist, but there are not enough cases per policy to claim policy-specific readiness.

### Business Impact Gaps

46. Generated data does not prove business impact.
    - The generated case has `business_impact_quality_score: 0.0`.
    - No assessment time saved, pilot avoided, blocker prevented, platform gap resolved, or decision outcome is recorded.

47. Outcome backlog is empty because there are no trusted labels.
    - `outcome-backlog` returned no cases.
    - The case needs review/adjudication before it becomes eligible for outcome follow-up.

48. Outcome request export is empty.
    - No trusted-label case exists, so there is nothing to request.
    - This is correct behavior but shows the workflow is not yet producing business evidence by itself.

49. Business impact records are not tied to external validation.
    - The schema can store impact fields, but it cannot verify time saved, pilot cost avoided, or decision value without an external accountable source.

50. No baseline comparator exists.
    - Business impact needs comparison against the previous process: manual review time, failed pilot rate, storage blocker discovery timing, and platform backlog quality.

51. No monetary model is implemented.
    - The project intentionally avoids pricing.
    - Business impact can be recorded operationally, but financial impact requires a separate model and governance.

52. No sales or platform funnel metrics exist.
    - The tool can support readiness conversations, but it does not track conversion, cycle time, adoption, expansion, or platform capability investments.

53. No SLA for decision usefulness exists.
    - There is no metric such as "percentage of REVIEW cases resolved by one follow-up" or "percentage of FAIL cases accepted by platform engineering."

54. No human-review cost model exists.
    - Review quality is scored, but there is no accounting for expert time by case type, uncertainty source, or policy pack.

55. No closed-loop correction mechanism exists.
    - Outcomes are recorded, but there is no automatic recommendation to adjust thresholds, reason text, or required evidence based on repeated false outcomes.

### Product And Operational Gaps

56. The collector still depends on local command availability.
    - Missing `iostat`, LVM tools, or restricted block commands reduce evidence quality.
    - There is no preflight that says which optional tools are installed before collection.

57. There is no collection mode matrix.
    - The tool needs documented evidence levels such as minimal, standard, storage-topology, owner-enriched, and calibration-grade.

58. There is no single command for the full audit workflow.
    - The workflow works, but requires multiple commands.
    - A `run-audit` orchestration command could produce bundle, profile snapshot, fit, validations, case, and summary in one local-only sequence.

59. No automatic artifact manifest for the whole audit directory exists.
    - Bundle manifest exists.
    - The higher-level audit outputs do not have a single manifest tying fit, validation, profile snapshot, corpus case, and coverage report together.

60. No quality gate policy file exists.
    - Validators emit warnings and scores, but there is no configurable gate such as "reject business review if topology score < 0.7 or path-purpose mismatch exists."

61. No release gate consumes all validators.
    - Tests pass and validators run manually.
    - A single release-readiness check should fail when corpus readiness, input realism, or decision validation regress.

62. No artifact signing or tamper-evident chain beyond checksums.
    - File checksums exist in the bundle manifest.
    - There is no signed chain of custody for high-stakes business use.

63. No versioned engine decision policy is embedded in every output.
    - Deep analysis has an engine version, but fit output needs enough rule/config/policy identifiers to reproduce decisions exactly.

64. No full explainability diff exists between two decisions.
    - `compare-evaluations` handles corpus metrics.
    - There is no decision-level diff showing why a workload changed from PASS to REVIEW or REVIEW to FAIL.

65. No governance around proprietary names beyond examples and warnings.
    - The repo avoids provider names.
    - A validator could scan profiles, cases, and examples for prohibited terms before publishing a bundle.

## Bottom Line

The current implementation is a credible local storage-fit preflight engine with honest validation boundaries. It generates realistic local input evidence and internally consistent output artifacts. It does not yet generate full empirical coverage, calibration-grade labels, or real business-impact evidence. The largest remaining step is not more UI or report polish; it is a closed-loop evidence program: high-quality real bundles, owner path-purpose declarations, expert reviews, adjudicated labels, decisive outcomes, and measured business-impact records across enough workload families and reason codes to make the technology defensible.

## Closure Status

Every gap above now has an implemented repository control in `docs/REALWORLD_GAP_CLOSURE_MATRIX.md`. The controls include CLI workflows, validators, quality gates, checksum manifests, coverage plans, business-impact summaries, and release gates. Gaps that require real external evidence are closed by explicit data contracts and gates, not by synthetic claims.
