# Gap Closure Ledger

This file records the real-world readiness gaps found during the local audit and the repository mechanisms that address them. The goal is to keep the project honest: a gap is not closed by prose alone, it must have a validator, command, score, schema, or testable workflow.

Status: closed in code and covered by tests as of the current repository state.

| ID | Gap | Closure in repo |
| --- | --- | --- |
| G01 | Evidence collection realism was too coarse. | Bundle validation now reports separate core, topology, application, redaction-preservation, and overall quality scores. |
| G02 | Redaction broke path semantics by replacing absolute paths with `path_001`. | Collector redaction now preserves absolute path shape under `/redacted/path_NNN/...` and emits a privacy-preserving `redaction-map.json`. |
| G03 | Process redaction removed useful workload identity. | Collector supports `strict`, `balanced`, and `none` process redaction modes while preserving executable/family signals. |
| G04 | Application ownership evidence was absent. | `create-case`, `check`, and validation accept app metadata, workload family, data paths, and path-purpose files. |
| G05 | Candidate mounts could be large non-app filesystems. | Candidate output now includes score, score reasons, ownership confidence, and false-positive risk. |
| G06 | `lsblk` and `findmnt` were attached but not used deeply. | Supplemental evidence now feeds device-lineage, mount-option, inode-pressure, and mapping-confidence analysis fields. |
| G07 | Optional topology command failures were underweighted. | Optional topology failures lower topology score and appear as collection issue codes. |
| G08 | `du` data was not generated. | `collect-du` creates explicit path-scoped summaries only for user-declared data paths. |
| G09 | Network filesystem warnings were noisy. | Decision validation/input realism distinguish candidate, session/system, and unknown network mounts. |
| G10 | Target profile provenance was generic. | `profile-snapshot` records checksum, fingerprint, origin, owner note, and source metadata. |
| G11 | Expert review workflow was too weak. | Case validation computes review quality and requires structured fields for calibration readiness. |
| G12 | Review quality gates were missing. | `validate-case` now blocks calibration readiness when review count/identity/confidence/reason agreement/adjudication is insufficient. |
| G13 | Outcome backlog was only implicit. | `outcome-backlog` and `export-outcome-requests` expose cases awaiting outcomes. |
| G14 | Outcome quality was not validated. | Outcome records are scored and decisive outcomes require date/status/source/confidence for calibration quality. |
| G15 | Business impact claims were unvalidated. | Impact records are scored; asserted impact without source/confidence is not counted as high-quality impact. |
| G16 | Full-coverage dataset requirements were not tracked. | `corpus-coverage` reports coverage gaps by workload family, reason code, outcome, and capability. |
| G17 | Policy-specific calibration was absent. | Corpus evaluation reports per-policy readiness and metrics. |
| G18 | Calibration math lacked comparisons/regression gates. | `compare-evaluations` reports accuracy/readiness/PASS failure-rate deltas. |
| G19 | Output realism was not checked. | `validate-decision` flags unsupported confidence, malformed redaction, missing analysis, and inconsistent requirements. |
| G20 | Input realism was not checked. | `validate-input-realism` checks manifest provenance, absolute paths, app evidence, process families, target profile origin, and topology gaps. |
| G21 | Business impact reporting lacked quality. | Corpus evaluation and summaries include business impact quality and decision metrics. |
| G22 | Synthetic and real data could be confused. | Cases and decisions carry `data_origin`, `profile_origin`, and calibration readiness excludes synthetic/untrusted cases. |
| G23 | End-to-end acceptance coverage was incomplete. | Workflow tests cover bundle, case, review, adjudication, outcome, impact, corpus, and CLI contracts. |
| G24 | The repo lacked explicit data contracts for all artifacts. | `schema` exposes versioned contracts for bundle manifests, cases, reviews, outcomes, impact, decisions, and calibration reports. |

## Verification

Run these commands after changes that touch evidence collection, inference, or corpus workflow:

```bash
python -m pytest -q

stateful-storage-fit collect \
  --output-dir out/local-bundle \
  --redact-first \
  --process-redaction-mode balanced

stateful-storage-fit collect-du \
  --bundle out/local-bundle \
  --data-path /data \
  --redact-paths

stateful-storage-fit check \
  --bundle out/local-bundle \
  --storage-profile examples/storage-profile.yml \
  --path-purpose examples/path-purpose.yml \
  --output out/fit.json

stateful-storage-fit validate-input-realism \
  --bundle out/local-bundle \
  --storage-profile examples/storage-profile.yml \
  --path-purpose examples/path-purpose.yml

stateful-storage-fit validate-decision \
  --decision out/fit.json

stateful-storage-fit corpus-coverage \
  --corpus-dir examples/corpus
```

The validation commands should be treated as release gates. A green unit test suite alone proves regression behavior, not business readiness.
