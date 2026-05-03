# Current Real-World Generator Audit

Audit date: 2026-04-30

Artifacts:

- `out/current-realworld-generator-audit/`
- `out/current-realworld-generator-audit/bundle/`
- `out/current-realworld-generator-audit/fit.json`
- `out/current-realworld-generator-audit/input-realism-generated-template.json`
- `out/current-realworld-generator-audit/input-realism-owner-sample.json`
- `out/current-realworld-generator-audit/quality-gate.json`
- `out/current-realworld-generator-audit/business-impact-summary.json`
- `out/current-realworld-generator-audit/coverage-plan.json`
- `out/current-realworld-generator-audit/audit-manifest.json`

## Commands Exercised

The current workflow exercised:

- `pytest -q`
- `tool-preflight`
- `evidence-modes`
- `collect`
- `collect-du`
- `path-purpose-template`
- `profile-snapshot`
- `validate-bundle`
- `validate-input-realism`
- `check`
- `validate-decision`
- `evidence-questions`
- `create-case`
- `validate-case`
- `quality-gate`
- `business-impact-summary`
- `corpus-summary`
- `corpus-coverage`
- `coverage-plan`
- `evaluate-corpus`
- `calibration-actions`
- `proprietary-scan`
- `audit-manifest`
- `decision-diff`
- `run-audit`

## Test Result

```text
50 passed
```

## Generated Input Validation

The local data generator produced a valid evidence bundle, but not a full-coverage or calibration-grade bundle.

Observed bundle metrics:

- Bundle valid: `true`
- Core completeness score: `1.0`
- Topology completeness score: `0.429`
- Application evidence score: `0.5`
- Redaction preservation score: `1.0`
- Overall bundle quality score: `0.811`
- Empty or failed optional topology outputs:
  - `blkid.txt`
  - `pvs.txt`
  - `vgs.txt`
  - `lvs.txt`

Input realism with static example path-purpose:

- Valid: `true`
- Path-purpose quality score: `70.0`
- Warnings:
  - `DECLARED_APP_PATH_NOT_OBSERVED_IN_MOUNT_OUTPUT`
  - `IOSTAT_SAMPLE_SHORT_FOR_CALIBRATION`
  - `PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC`
  - `TOPOLOGY_EVIDENCE_LOW`

Input realism with generated path-purpose template:

- Valid: `true`
- Path-purpose quality score: `60.0`
- Warnings:
  - `IOSTAT_SAMPLE_SHORT_FOR_CALIBRATION`
  - `PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC`
  - `TOPOLOGY_EVIDENCE_LOW`

Generated path-purpose template:

- Matches the observed redacted mount path.
- Marks ownership fields as `owner_required`.
- Does not claim real owner confirmation.

Scoped `du` evidence:

- Generated successfully.
- Measured the explicitly supplied examples path.
- Does not prove that path is complete application data.

## Generated Output Validation

The generated storage-fit output is internally consistent and realistic for the available evidence.

Fit result:

- Fit status: `REVIEW`
- Recommended storage class: `fast-rwo`
- Confidence: `MEDIUM`
- Capacity risk: `MEDIUM`
- Latency risk: `LOW`
- Missing data:
  - `iostat_device_mapping`
- Warnings:
  - `NETWORK_FILESYSTEM_ON_NON_DATA_MOUNT`
  - `IOSTAT_DEVICE_MAPPING_UNCERTAIN`
  - `TOPOLOGY_EVIDENCE_LOW`
- Blockers: none
- Decision validation: valid

The result is appropriate because the generated inputs are incomplete for high-confidence business use. A `PASS` would be too strong.

## Business-Impact Validation

The business-impact workflow behaved correctly: it refused to infer impact from generated data.

Business-impact summary:

- Claim status: `EVIDENCE_MISSING`
- Case count: `1`
- Impact record count: `0`
- High-quality impact record count: `0`

Case validation:

- Case valid: `true`
- Trusted label: `false`
- Calibration ready: `false`
- Review quality score: `0.0`
- Outcome quality score: `0.0`
- Business impact quality score: `0.0`

Quality gate:

- Gate status: `REVIEW`
- Passed: `false`
- Issues:
  - `TOPOLOGY_EVIDENCE_BELOW_GATE`
  - `BUNDLE_QUALITY_BELOW_GATE`
  - `GENERIC_PROFILE_BLOCKED_FOR_BUSINESS_REVIEW`
- Warnings:
  - `CASE_HAS_NO_TRUSTED_LABEL`

This is the correct behavior. The tool can generate an audit record, but it cannot generate business impact without external review, outcomes, and measured operational impact.

## Corpus And Coverage Validation

Example corpus result:

- Case count: `3`
- Trusted label count: `0`
- Outcome-linked case count: `0`
- Synthetic decision accuracy: `1.0`
- Readiness: `RESEARCH_ONLY`

Coverage plan:

- Generated `10` calibration-grade data requests.
- The requests target missing workload-family and reason-code coverage.

Calibration actions:

- Add decisive outcome records for trusted-label cases.
- Prioritize outcome follow-up for older reviewed cases.
- Add independent expert reviews or adjudication before outcome requests.

## Current Extensive Gap List

### A. Input Data Gaps

1. Tool availability does not guarantee useful output.
   - `tool-preflight` reported optional tool coverage as `1.0`.
   - `blkid`, `pvs`, `vgs`, and `lvs` still produced empty or failed outputs.

2. Topology completeness remains below business-review gate.
   - Observed topology completeness was `0.429`.

3. Bundle quality remains below the configured gate.
   - Observed bundle quality was `0.811`, below the example gate threshold of `0.85`.

4. The default `iostat` sample is too short for calibration.
   - `iostat_reports_seen` was `5`.
   - The validator emitted `IOSTAT_SAMPLE_SHORT_FOR_CALIBRATION`.

5. Device-to-iostat mapping remains uncertain.
   - Fit output included `IOSTAT_DEVICE_MAPPING_UNCERTAIN`.

6. Generated path-purpose data is a template, not owner confirmation.
   - It correctly uses `owner_required` and `REQUIRES_OWNER`.
   - It cannot prove ownership, writer topology, or read/write behavior.

7. Static sample path-purpose can mismatch observed mounts.
   - The example declared `/data`.
   - The local collected bundle observed a redacted mount path instead.

8. Path-purpose quality is still below high-confidence use.
   - Generated template score was `60.0`.
   - Static example score was `70.0` but had a path mismatch.

9. Process evidence is not application-rich.
   - The useful process list only contained generic local process evidence from the audit host.

10. Process evidence remains point-in-time.
    - It may miss inactive services, scheduled jobs, failover processes, backup jobs, and maintenance windows.

11. `du` evidence is path-scoped, not workload-complete.
    - It measured only the explicitly supplied path.
    - It does not prove the measured path is the full workload data set.

12. `du` evidence did not align with the detected candidate data mount.
    - The measured examples path is useful for testing the mechanism, not for proving the candidate mount is application data.

13. The storage profile is still generic.
    - Input validation emitted `PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC`.

14. Profile snapshot proves artifact integrity, not target-platform truth.
    - It records checksum, fingerprint, and metadata.
    - It cannot prove current target storage configuration without a trusted offline export or owner attestation.

15. Network filesystem context remains underexplained.
    - Output included `NETWORK_FILESYSTEM_ON_NON_DATA_MOUNT`.
    - The tool detects the signal but does not know its business purpose.

16. No workload time-window metadata was generated.
    - The run does not identify whether data was collected during idle, peak, backup, maintenance, or incident periods.

17. No growth-rate history was generated.
    - Capacity remains a point-in-time estimate plus heuristic headroom.

18. No retention, purge, archive, compression, or churn evidence was generated.

19. No file-size distribution or directory fanout evidence was generated.
    - Inode summary exists, but detailed metadata workload shape is unknown.

20. No write-consistency evidence was generated.
    - The inputs do not prove fsync, file locking, crash recovery, or write ordering assumptions.

21. No multi-VM topology evidence was generated.
    - RWX and active/passive behavior often require cross-host evidence.

22. No owner attestation was generated.
    - The tool correctly requires human/owner input instead of inventing it.

23. No application lifecycle metadata was generated.
    - There is no evidence of maintenance operations, backups, restores, failover, or batch periods.

24. No raw-device negative proof exists.
    - The tool did not find raw block hints, but absence in one snapshot is not proof.

25. No target storage-class quota or policy evidence exists beyond the supplied YAML.

### B. Output Data Gaps

26. The output is realistic but not decisive.
    - `REVIEW` is appropriate; it is not a high-confidence `PASS`.

27. The recommended storage class is only as real as the supplied profile.
    - `fast-rwo` is a generic example class.

28. Capacity risk is still heuristic.
    - It does not include growth or retention evidence.

29. Latency risk is based on a short sample.
    - It should not be interpreted as target-platform performance readiness.

30. Missing iostat mapping prevents high-confidence device risk attribution.

31. The decision has no hard blockers, but quality gate still blocks business use.
    - This distinction is correct but must be understood by users.

32. The output does not quantify false PASS/false REVIEW probability.
    - Corpus lacks outcome-linked calibration data.

33. Evidence questions exist as a follow-up artifact, but answers are not yet collected.

34. Decision validation checks internal consistency, not empirical truth.

35. Decision output includes engine policy evidence, but no signed chain of custody.

36. Decision diff self-check is stable, but no cross-version regression run was performed in this audit.

37. Redacted paths preserve shape but not business meaning.
    - Owner-held mapping is still needed.

38. The fit result does not prove migration safety or container readiness.
    - This remains an explicit project boundary.

### C. Business-Impact Gaps

39. No business-impact record exists.
    - Impact record count is `0`.

40. No high-quality impact evidence exists.
    - High-quality impact record count is `0`.

41. No assessment-time savings were measured.

42. No avoided failed pilot was recorded.

43. No platform capability gap acceptance was recorded.

44. No decision outcome was recorded.

45. No accountable business-impact source was recorded.

46. Baseline comparator exists, but no real case impact data exists to compare.

47. The business-impact summary correctly reports `EVIDENCE_MISSING`.

48. The generated data cannot prove revenue, cost, conversion, or cycle-time value.
    - The tool intentionally avoids pricing and sales-funnel claims.

49. Review effort cannot be modeled yet because there are no expert review records.

50. The gate correctly prevents business-ready claims, but users still need operational process around follow-up.

### D. Corpus And Calibration Gaps

51. Example corpus remains synthetic and small.
    - Case count is `3`.

52. Trusted label count is `0`.

53. Outcome-linked case count is `0`.

54. Corpus readiness remains `RESEARCH_ONLY`.

55. Synthetic accuracy is not empirical defensibility.
    - Decision accuracy is `1.0` only against synthetic examples.

56. Coverage plan still requires calibration-grade cases.
    - It generated `10` requests.

57. Workload-family coverage remains incomplete.

58. Reason-code coverage remains incomplete.

59. Capability coverage remains incomplete.

60. No negative-control real cases exist.

61. No borderline-threshold real cases exist.

62. No malformed-real-input corpus exists.

63. No temporal-repeat corpus exists.

64. No cross-reviewer disagreement corpus exists at scale.

65. No profile-drift corpus exists.

66. No policy-pack-specific readiness exists.

67. Outcome backlog remains structurally correct but empty until trusted labels exist.

68. Outcome request export remains structurally correct but empty until trusted labels exist.

### E. Governance And Operational Gaps

69. The workflow is now orchestrated, but sequencing still matters when commands are run manually.
    - A parallel gate attempt failed before `case-validation.json` existed.
    - `run-audit` avoids this by sequencing artifacts.

70. Tool preflight needs to distinguish command availability from command usefulness.
    - Tools existed, but several produced empty/failed outputs.

71. Quality gate policy is example-based.
    - Real organizations need their own thresholds.

72. Proprietary scan depends on user-supplied terms.
    - The repo intentionally does not bundle provider/customer name lists.

73. Audit manifest is checksum-based, not cryptographically signed.

74. There is no external attestation workflow for storage profile truth.

75. There is no external attestation workflow for owner path-purpose truth.

76. There is no follow-up SLA engine for evidence questions.

77. There is no reminder/escalation workflow for outcome lag.

78. There is no automatic threshold tuning.
    - `calibration-actions` identifies actions, but does not rewrite rules.

79. There is no multi-run trend report for one workload over time.

80. There is no packaged handoff archive command yet.

## Assessment

The generator now produces appropriate local evidence for a deterministic storage-fit audit and the validators correctly distinguish structural validity from business readiness. The generated output is realistic because it returns `REVIEW`, not an unsupported `PASS`, and the quality gate blocks business-ready claims.

The generator does not and should not claim full coverage by itself. Full coverage requires owner-confirmed path purpose, longer and representative performance samples, stronger topology evidence, real target profile provenance, expert review, adjudication where needed, decisive outcomes, and measured business-impact records.

## Resolution Update

The 80 gaps in this audit are tracked to closure in `docs/CURRENT_REALWORLD_GAP_RESOLUTION_PROGRESS.md`.

The closure keeps the critical evidence boundary intact: generated full-coverage data now exercises the product surface and business-impact workflow, but measured business-impact and empirical calibration claims remain blocked until non-generated owner, reviewer, outcome, and impact evidence exists.
