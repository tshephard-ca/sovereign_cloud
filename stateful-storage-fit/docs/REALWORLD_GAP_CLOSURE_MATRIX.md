# Real-World Gap Closure Matrix

This file maps every gap from `docs/REALWORLD_DATA_AUDIT_GAPS.md` to a concrete repository mechanism. Some gaps cannot be closed by generated data without inventing evidence. For those gaps, the repo closure is an enforceable workflow, validator, quality gate, or required data contract that prevents unsupported business or calibration claims.

## Closure Commands

- `tool-preflight`: checks local command availability before collection.
- `evidence-modes`: documents minimal, standard, owner-enriched, and calibration-grade evidence levels.
- `path-purpose-template`: generates an owner-confirmation template from observed candidate mounts.
- `validate-input-realism`: validates bundle realism, path-purpose quality, iostat sample length, profile genericness, topology score, and network filesystem context.
- `validate-decision`: validates decision consistency.
- `quality-gate`: applies configurable business, calibration, or release gates.
- `run-audit`: executes the local audit workflow into one output directory.
- `audit-manifest`: creates a checksum manifest for the full audit artifact directory.
- `decision-diff`: explains decision changes between two fit JSON files.
- `evidence-questions`: exports follow-up questions from REVIEW decisions.
- `coverage-plan`: turns corpus coverage gaps into calibration-grade case requests.
- `business-impact-summary`: summarizes measured operational impact without pricing.
- `calibration-actions`: converts corpus readiness blockers into action items.
- `proprietary-scan`: scans artifacts against a user-supplied banned-term list.

## Closure Matrix

| Gap | Closure Status | Repository Closure |
| --- | --- | --- |
| 1 | Addressed by validation and preflight | `tool-preflight`, `validate-bundle`, and `validate-input-realism` expose missing optional topology tools and failed outputs as scores and issue codes. |
| 2 | Addressed by quality gate | `quality-gate` blocks business/release use when topology completeness is below policy. |
| 3 | Addressed by template generation | `path-purpose-template` generates owner-confirmation path-purpose YAML from observed candidate mounts. |
| 4 | Addressed by data contract | `path-purpose` schema, `path-purpose-template`, and `validate-input-realism` require explicit owner confirmation rather than inference. |
| 5 | Addressed by bounded redaction and warning | balanced process redaction preserves executable signals; validators avoid treating process evidence as full topology proof. |
| 6 | Addressed by evidence-mode boundary | `evidence-modes` identifies process-list evidence as non-calibration-grade without owner enrichment and outcomes. |
| 7 | Addressed by sample-length validation | `validate-input-realism` emits `IOSTAT_SAMPLE_SHORT_FOR_CALIBRATION` for short samples. |
| 8 | Addressed by supplemental topology and gate | `lsblk`/`findmnt` enrichment, `IOSTAT_DEVICE_MAPPING_UNCERTAIN`, and `quality-gate` prevent high-confidence use when mapping is weak. |
| 9 | Addressed by classification | `validate-input-realism` separates data-like, system/session, and unknown network filesystem mounts. |
| 10 | Addressed by scoped data contract | `collect-du` only records explicitly supplied paths; path-purpose quality and gate checks prevent treating it as complete ownership proof. |
| 11 | Addressed by path-preserving redaction | collector/report redaction uses `/redacted/path_NNN/...`; path-purpose mismatch validation catches unresolved mappings. |
| 12 | Addressed by profile realism validation | `validate-input-realism` warns on example-generic profiles and `quality-gate` can block them. |
| 13 | Addressed by profile snapshot | `profile-snapshot` records checksum, fingerprint, origin, and source metadata while preserving the offline boundary. |
| 14 | Addressed by score | `validate-input-realism` reports `path_purpose_quality_score`. |
| 15 | Addressed by evidence-level contract | `evidence-modes` and `quality-gate` define owner-enriched/calibration-grade requirements; collection-window fields remain owner-supplied evidence. |
| 16 | Addressed by required external evidence path | `coverage-plan` and evidence modes require real owner/outcome records for growth-sensitive calibration instead of generated assumptions. |
| 17 | Addressed by supplemental inode evidence and gate | `inode-df.txt` is collected; inode risk is surfaced and low evidence remains gateable. |
| 18 | Addressed by follow-up questions | `evidence-questions` exports unanswered consistency/write-safety questions for REVIEW closure. |
| 19 | Addressed by candidate scoring and owner confirmation | candidate score, false-positive risk, path-purpose templates, and quality gates prevent unconfirmed ownership claims. |
| 20 | Addressed by boundary and evidence mode | one-VM scope is explicit; multi-VM relationship data is required owner evidence for calibration-grade use. |
| 21 | Addressed by gate | valid REVIEW decisions can be blocked from business/release use by `quality-gate`. |
| 22 | Addressed by language and gate | decision language remains risk-based; high-risk or short-sample cases require deeper testing via REVIEW/gate outcomes. |
| 23 | Addressed by caveat and follow-up | capacity remains heuristic; coverage plans and owner evidence requests require growth/retention validation for calibration-grade use. |
| 24 | Addressed by profile snapshot and decision policy evidence | fit output records engine policy/config identifiers; profile snapshot records supplied class semantics. |
| 25 | Addressed by redaction map and owner mapping workflow | path shape is preserved and mismatch checks force owner-held mapping resolution. |
| 26 | Addressed by closed-loop export | `evidence-questions` exports REVIEW questions into a trackable artifact. |
| 27 | Addressed by honesty boundary | validators check consistency and realism; quality gates prevent treating validator-clean data as truth without reviews/outcomes. |
| 28 | Addressed by empirical calibration workflow | corpus evaluation reports false outcome rates once real outcome data exists; categorical confidence remains conservative until then. |
| 29 | Addressed by decision diff and gate | blockers remain explicit; business reversibility is captured through review/outcome/impact records and gate policy. |
| 30 | Addressed by machine artifacts and impact summaries | JSON remains primary; `business-impact-summary`, `evidence-questions`, and case records support persona-specific handoff without unsupported claims. |
| 31 | Addressed by coverage planning | `coverage-plan` reports required calibration-grade cases beyond the synthetic example corpus. |
| 32 | Addressed by review quality gates | `validate-case` and `quality-gate` require trusted labels for calibration/release use. |
| 33 | Addressed by outcome workflow | `outcome-backlog`, `export-outcome-requests`, and `validate-case` require decisive outcomes for calibration readiness. |
| 34 | Addressed by release gate | `quality-gate --mode release` fails when corpus readiness remains research-only. |
| 35 | Addressed by family coverage targets | `corpus-coverage` and `coverage-plan` identify family case deficits. |
| 36 | Addressed by reason-code coverage targets | `corpus-coverage` and `coverage-plan` identify reason-code deficits. |
| 37 | Addressed by capability coverage reporting | `corpus-coverage` reports RWX, block, and fast-block demand; coverage plans request missing cases. |
| 38 | Addressed by coverage plan workflow | negative-control cases are requested as calibration-grade data rather than generated as fake truth. |
| 39 | Addressed by coverage plan workflow | borderline cases are requested through coverage planning and policy-pack regression tests. |
| 40 | Addressed by parser tests and coverage plan | malformed input remains a required fixture category in the closure matrix and can be added as corpus cases. |
| 41 | Addressed by case/corpus model | temporal repeats are represented as separate cases with shared metadata and compared by `decision-diff`. |
| 42 | Addressed by adjudication workflow | conflicting reviews produce `REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION`. |
| 43 | Addressed by outcome requests | outcome backlog/export commands create the follow-up worklist for lagging outcomes. |
| 44 | Addressed by snapshot and diff | profile snapshots and decision diffs identify profile drift effects. |
| 45 | Addressed by policy-specific evaluation path | policy pack paths are recorded in cases and evaluation readiness remains gated by real cases. |
| 46 | Addressed by impact quality gate | generated cases remain `EVIDENCE_MISSING`; impact claims require high-quality business-impact records. |
| 47 | Addressed by lifecycle gate | outcome backlog remains empty until trusted labels exist; this prevents premature outcome requests. |
| 48 | Addressed by outcome request gate | empty outcome requests are correct until review/adjudication creates trusted labels. |
| 49 | Addressed by source/confidence fields | impact records require source and confidence for high quality; summaries do not verify external truth. |
| 50 | Addressed by baseline comparator | `business-impact-summary --baseline` compares operational minutes to a user-supplied baseline. |
| 51 | Addressed by explicit boundary | no pricing model is implemented; operational impact is recorded without monetary estimates. |
| 52 | Addressed by impact/portfolio artifacts | portfolio and impact summaries expose operational metrics without turning the tool into a sales system. |
| 53 | Addressed by quality metrics | corpus summaries, evidence questions, and business-impact summaries provide measurable decision usefulness inputs. |
| 54 | Addressed by review and impact time fields | expert review minutes and assessment minutes are recorded and summarized. |
| 55 | Addressed by calibration actions | `calibration-actions` turns readiness blockers and mismatches into threshold/review follow-up actions. |
| 56 | Addressed by tool preflight | `tool-preflight` reports required and optional command availability before collection. |
| 57 | Addressed by evidence modes | `evidence-modes` defines the collection mode matrix. |
| 58 | Addressed by orchestration | `run-audit` generates the primary audit artifacts in one local-only command. |
| 59 | Addressed by audit manifest | `audit-manifest` creates a checksum manifest for the full audit directory. |
| 60 | Addressed by gate policy | `quality-gate` supports configurable thresholds via YAML. |
| 61 | Addressed by release gate | `quality-gate --mode release` consumes validation/corpus reports and blocks research-only evidence. |
| 62 | Addressed by tamper-evident checksum chain | `audit-manifest` provides checksums; it explicitly states no signing key is used. |
| 63 | Addressed by engine policy evidence | fit output includes engine version, thresholds, config path/hash, and policy-pack path/hash. |
| 64 | Addressed by decision diff | `decision-diff` explains fit, requirement, risk, warning, reason-code, and blocker changes. |
| 65 | Addressed by user-supplied governance scan | `proprietary-scan` scans artifacts against a user-supplied banned-term list; no provider/customer name list is bundled. |

## Final Boundary

All 65 gaps now have a concrete repository control. Gaps that require real data are not "solved" by generating synthetic evidence; they are closed by enforceable requirements, gates, and worklists that force real owner, reviewer, outcome, and impact data before calibration or business-impact claims are allowed.
