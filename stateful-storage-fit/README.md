# stateful-storage-fit

## What the tool does

`stateful-storage-fit` is a local-only storage preflight for one VM-based stateful workload. It reads ordinary Linux text outputs plus a user-supplied storage profile YAML and answers one narrow question:

> Can this workload's observed storage shape plausibly fit one of the target PersistentVolume options?

## What it does not do

It does not migrate applications, generate manifests, create PVCs, inspect clusters, price storage, test application correctness, prove container readiness, infer all application dependencies, rewrite secrets, build CI/CD, connect to a cluster, or call external services.

## Why this exists

Persistent storage is a common blocker in moving stateful workloads from VMs to Kubernetes/OpenShift-compatible platforms. Storage classes, access modes, volume modes, capacity, and performance tiers must match the workload's actual storage behavior. This tool keeps the check small, deterministic, and offline.

## Quickstart

```bash
stateful-storage-fit check \
  --df examples/vm1/df.txt \
  --mount examples/vm1/mount.txt \
  --fstab examples/vm1/fstab.txt \
  --iostat examples/vm1/iostat.txt \
  --ps examples/vm1/ps.txt \
  --storage-profile examples/storage-profile.yml \
  --output out/fit.json \
  --mount-report out/mounts.csv
```

Optional flags:

```bash
--redact
--strict
--data-path /data
--data-path /var/lib/postgresql
--config examples/thresholds.yml
--policy-pack examples/policy-packs/relational-database.yml
--path-purpose examples/path-purpose.yml
--app-name workload-001
--workload-family relational_database
--format json
```

The JSON output preserves the original top-level PASS / REVIEW / FAIL contract and also includes an `analysis` object. That object contains a normalized evidence graph, a storage behavior fingerprint, enhanced requirements, per-storage-class compatibility constraints, and evidence questions for REVIEW cases.

## Core technology model

The project is structured around a storage compatibility inference pipeline:

1. Parse local VM evidence.
2. Normalize observations into an evidence graph.
3. Infer a storage behavior fingerprint.
4. Convert the fingerprint into formal storage requirements.
5. Solve those requirements against the supplied storage profile.
6. Identify the missing facts most likely to change the decision.

This keeps the deterministic CLI useful while making the core decision layer inspectable and testable.

Key internal artifacts:

- `EvidenceGraph`: observed facts, inferences, missing facts, and parse warnings.
- `StorageBehaviorFingerprint`: inferred storage behavior such as shared namespace dependency, writer topology, sync-write sensitivity, raw block likelihood, expansion need, and evidence quality.
- `EnhancedStorageRequirement`: hard requirements, soft preferences, and unresolved requirement dimensions.
- `StorageClassCompatibility`: hard failures, soft warnings, satisfied constraints, scores, and counterfactuals for each storage class.
- `EvidenceQuestion`: the next local fact or human answer that would most reduce uncertainty.

## Collection commands

The tool accepts user-supplied text files and does not require a specific collector. These commands produce useful inputs on many Linux systems:

```bash
df -PT -B1
mount
cat /etc/fstab
iostat -x -d -m 1 5
ps -eo pid,comm,args --no-headers
```

Process arguments may contain secrets. Use `--redact` for handoff outputs when process arguments or non-system paths should not be shown. For collected bundles, `--redact-first` writes redacted evidence and keeps non-system paths absolute under `/redacted/path_NNN/...` so mount hierarchy is still analyzable.

## Optional local collector

The core tool never collects automatically. If a user explicitly wants a local bundle, run:

```bash
stateful-storage-fit collect \
  --output-dir out/local-bundle \
  --redact-first \
  --process-redaction-mode balanced
```

This writes local command outputs and a `manifest.json` with collector version, timestamp, command return codes, safe host facts, file checksums, redaction mode, and a bundle fingerprint. Optional commands such as `findmnt --json`, `lsblk --json`, `blkid`, `pvs`, `vgs`, and `lvs` are best-effort and may be unavailable on some systems. No SSH, credentials, cluster access, telemetry, or external services are used.

If a workload owner has declared data paths, collect explicit path-scoped size evidence:

```bash
stateful-storage-fit collect-du \
  --bundle out/local-bundle \
  --data-path /data \
  --data-path /var/lib/postgresql \
  --redact-paths
```

`collect-du` only measures paths the user supplies. It does not crawl for application data on its own.

Validate a bundle:

```bash
stateful-storage-fit validate-bundle \
  --bundle out/local-bundle \
  --output out/bundle-validation.json
```

Supplemental evidence can be passed to `check`:

```bash
stateful-storage-fit check \
  --df out/local-bundle/df.txt \
  --mount out/local-bundle/mount.txt \
  --fstab out/local-bundle/fstab.txt \
  --iostat out/local-bundle/iostat.txt \
  --ps out/local-bundle/ps.txt \
  --findmnt-json out/local-bundle/findmnt.json \
  --lsblk-json out/local-bundle/lsblk.json \
  --blkid out/local-bundle/blkid.txt \
  --pvs out/local-bundle/pvs.txt \
  --vgs out/local-bundle/vgs.txt \
  --lvs out/local-bundle/lvs.txt \
  --storage-profile examples/storage-profile.yml
```

Or use the bundle directly:

```bash
stateful-storage-fit check \
  --bundle out/local-bundle \
  --storage-profile examples/storage-profile.yml \
  --path-purpose examples/path-purpose.yml \
  --output out/fit.json
```

## Storage profile

The user must describe the target platform's storage options in YAML. The project does not know proprietary storage classes. The storage profile is the contract.

Required profile rules:

- `storage_classes` is required.
- `name`, `access_modes`, `volume_modes`, `storage_kind`, and `performance_tier` are required for each class.
- `storage_kind` must be `block`, `file`, `local`, or `unknown`.
- `performance_tier` must exist in `performance_tiers`.
- `max_size_gib` is optional.
- `supports_expansion` and `supports_snapshots` default to `false`.

See `examples/storage-profile.yml` for a generic profile.

Create a profile provenance snapshot:

```bash
stateful-storage-fit profile-snapshot \
  --storage-profile examples/storage-profile.yml \
  --origin user_supplied \
  --source-metadata examples/profile-source-metadata.yml \
  --output out/storage-profile-snapshot.json
```

The snapshot records a checksum and normalized fingerprint. It still does not imply the tool knows any proprietary storage class.

## Policy packs

Policy packs are optional offline YAML files that adjust thresholds and required-evidence expectations for a workload family. They do not add proprietary platform knowledge and do not change the local-only boundary.

Examples:

- `examples/policy-packs/relational-database.yml`
- `examples/policy-packs/file-server.yml`

Policy packs are deliberately versioned because rule changes must be auditable.

## Output interpretation

`PASS` means storage fit looks plausible for at least one supplied storage class and no hard blocker was found.

`REVIEW` means there is a plausible fit, but a human should check highlighted risks such as missing data, high observed latency risk, root-only storage visibility, file-serving behavior, raw block hints, or uncertain device mapping.

`FAIL` means the supplied storage profile lacks an observed required capability such as ReadWriteMany filesystem support, Block volume mode, sufficient size, or a matching performance tier.

None of these decisions mean the application is fully migration-ready.

## Portfolio mode

Portfolio mode analyzes many offline VM evidence bundles from an inventory YAML:

```bash
stateful-storage-fit portfolio \
  --inventory examples/portfolio.yml \
  --output out/portfolio.json
```

The output summarizes PASS / REVIEW / FAIL counts, top blockers, reason-code counts, storage capability demand, missing evidence counts, and per-workload decisions. This is useful for platform capability planning, not migration wave planning.

## Corpus evaluation

The repo includes a synthetic corpus format for regression testing and future expert/outcome-labeled cases:

```bash
stateful-storage-fit evaluate-corpus \
  --corpus-dir examples/corpus \
  --output out/corpus-eval.json
```

Each case can include expected fit status, expected requirement fields, labels, reviewer notes, and future outcome labels. Synthetic corpus accuracy is not a claim about real-world accuracy; real defensibility requires expert-reviewed and outcome-linked cases.

### Resolving the validation boundary

The core technology does not treat synthetic fixtures as proof. Corpus cases support three progressively stronger evidence levels:

- `synthetic`: useful for regression tests and parser/rule coverage.
- `expert_consensus`: one or more expert reviews agree on fit status and requirements.
- `outcome_linked`: a real assessment outcome confirms success, storage fit, storage blocker, failed storage assumption, or storage rework.

Create a case template:

```bash
stateful-storage-fit case-template \
  --case-id workload-001 \
  --output corpus/workload-001.yml
```

Outcome statuses used for calibration:

- `onboarded_successfully`
- `storage_fit_confirmed`
- `blocked_by_storage`
- `failed_storage_assumption`
- `storage_rework_required`
- `blocked_by_non_storage`
- `not_attempted`
- `unknown`

Only decisive storage-relevant outcomes calibrate the engine: successful storage fit or storage failure/rework. `unknown`, `not_attempted`, and non-storage blockers remain case history but do not strengthen readiness.

`evaluate-corpus` computes:

- decision accuracy against expected or reviewed labels
- requirement-field accuracy
- expert/trusted label coverage
- decisive outcome coverage
- PASS storage-failure rate
- outcome metrics by predicted status
- outcome metrics by reason code
- readiness level: `RESEARCH_ONLY`, `CALIBRATED_INTERNAL`, or `PRODUCTION_READY`

Example:

```bash
stateful-storage-fit evaluate-corpus \
  --corpus-dir corpus \
  --min-outcome-cases 20 \
  --min-outcome-coverage 0.30 \
  --max-pass-storage-failure-rate 0.10 \
  --output out/calibration.json
```

Use that calibration artifact during future checks:

```bash
stateful-storage-fit check \
  --df examples/vm1/df.txt \
  --mount examples/vm1/mount.txt \
  --fstab examples/vm1/fstab.txt \
  --iostat examples/vm1/iostat.txt \
  --ps examples/vm1/ps.txt \
  --storage-profile examples/storage-profile.yml \
  --calibration out/calibration.json
```

If the corpus is still `RESEARCH_ONLY`, the check result includes calibration warnings and caps confidence conservatively. The code therefore resolves the boundary by making validation state explicit and enforceable rather than by inventing unsupported confidence.

### Complete real-world data workflow

The project can now generate and maintain the full data trail required for empirical calibration:

```text
evidence bundle
-> storage profile snapshot
-> engine decision record
-> expert reviews
-> adjudication
-> outcome record
-> business impact record
-> corpus evaluation
-> calibration artifact
```

List versioned data contracts:

```bash
stateful-storage-fit schema
stateful-storage-fit schema --name corpus-case
stateful-storage-fit schema --name calibration-report
stateful-storage-fit schema --name input-realism-report
```

Create a corpus case from a collected bundle:

```bash
stateful-storage-fit create-case \
  --case-id workload-001 \
  --bundle out/local-bundle \
  --storage-profile examples/storage-profile.yml \
  --path-purpose examples/path-purpose.yml \
  --app-name workload-001 \
  --workload-family relational_database \
  --data-origin real_workload \
  --profile-origin user_supplied \
  --output corpus/workload-001.yml
```

The created case includes:

- bundle path, manifest path, bundle validation, and bundle fingerprint
- storage profile snapshot and profile checksum
- engine decision record with evidence graph and compatibility analysis
- empty `expert_reviews`, `adjudication`, `outcomes`, and `business_impact` sections

Validate a case:

```bash
stateful-storage-fit validate-case \
  --case corpus/workload-001.yml
```

Validate the raw inputs and the emitted decision before using them for business review:

```bash
stateful-storage-fit tool-preflight
stateful-storage-fit evidence-modes

stateful-storage-fit validate-input-realism \
  --bundle out/local-bundle \
  --storage-profile examples/storage-profile.yml \
  --path-purpose examples/path-purpose.yml \
  --output out/input-realism.json

stateful-storage-fit validate-decision \
  --decision out/fit.json \
  --output out/decision-validation.json

stateful-storage-fit quality-gate \
  --input-realism out/input-realism.json \
  --decision-validation out/decision-validation.json \
  --case-validation out/case-validation.json \
  --gate-config examples/quality-gate.yml \
  --output out/quality-gate.json
```

Append expert reviews:

```bash
stateful-storage-fit add-review \
  --case corpus/workload-001.yml \
  --review review-a.yml

stateful-storage-fit add-review \
  --case corpus/workload-001.yml \
  --review review-b.yml
```

If reviews agree, adjudication can promote consensus:

```bash
stateful-storage-fit adjudicate-case \
  --case corpus/workload-001.yml
```

If reviews disagree, provide an adjudication YAML:

```bash
stateful-storage-fit adjudicate-case \
  --case corpus/workload-001.yml \
  --adjudication adjudication.yml
```

Append a real outcome:

```bash
stateful-storage-fit add-outcome \
  --case corpus/workload-001.yml \
  --status storage_fit_confirmed \
  --notes "Storage fit confirmed by platform review."
```

Append business impact data:

```bash
stateful-storage-fit add-impact \
  --case corpus/workload-001.yml \
  --assessment-minutes 45 \
  --expert-review-minutes 20 \
  --blocker-found-before-pilot false \
  --failed-pilot-avoided false \
  --platform-gap-identified false \
  --decision proceed
```

Summarize case lifecycle and outcome backlog:

```bash
stateful-storage-fit corpus-summary \
  --corpus-dir corpus \
  --output out/corpus-summary.json

stateful-storage-fit outcome-backlog \
  --corpus-dir corpus \
  --output out/outcome-backlog.json

stateful-storage-fit export-outcome-requests \
  --corpus-dir corpus \
  --output out/outcome-requests.json

stateful-storage-fit corpus-coverage \
  --corpus-dir corpus \
  --output out/corpus-coverage.json
```

Compare calibration runs before changing release posture:

```bash
stateful-storage-fit compare-evaluations \
  --old out/corpus-eval-previous.json \
  --new out/corpus-eval-current.json \
  --output out/evaluation-comparison.json

stateful-storage-fit calibration-actions \
  --corpus-evaluation out/corpus-eval-current.json \
  --output out/calibration-actions.json
```

Generate a single local-only audit directory from an existing bundle:

```bash
stateful-storage-fit run-audit \
  --output-dir out/audit \
  --bundle out/local-bundle \
  --storage-profile examples/storage-profile.yml \
  --path-purpose examples/path-purpose.yml \
  --app-name workload-001 \
  --workload-family relational_database
```

Create additional governance artifacts:

```bash
stateful-storage-fit path-purpose-template \
  --bundle out/local-bundle \
  --output out/path-purpose-template.yml

stateful-storage-fit audit-manifest \
  --audit-dir out/audit \
  --output out/audit/audit-manifest.json

stateful-storage-fit decision-diff \
  --old out/fit-before.json \
  --new out/fit-after.json

stateful-storage-fit evidence-questions \
  --decision out/fit.json

stateful-storage-fit coverage-plan \
  --corpus-dir corpus

stateful-storage-fit business-impact-summary \
  --corpus-dir corpus \
  --baseline examples/business-impact-baseline.yml

stateful-storage-fit proprietary-scan \
  --path out/audit \
  --banned-terms examples/banned-terms.txt
```

This workflow is the intended path to real business impact. A case becomes a trusted label through expert consensus or adjudication. It becomes calibration evidence only when it has a decisive storage-relevant outcome. Business impact records quantify assessment time, expert review time, blockers found before pilots, failed pilots avoided, platform gaps identified, and decisions made.

## Reason-code dictionary

- `DATA_MOUNT_DETECTED`: a likely data mount was identified.
- `ROOT_ONLY_STORAGE_VIEW`: only `/` was usable as a data candidate.
- `SHARED_FS_DETECTED`: a candidate data mount uses a shared or network filesystem.
- `DB_PROCESS_DETECTED`: a database-like process name was observed.
- `STATEFUL_PROCESS_DETECTED`: a message, log, search, or stateful service process name was observed.
- `FILE_SERVER_PROCESS_DETECTED`: a file-serving process name was observed.
- `BLOCK_STORAGE_PREFERRED`: block-backed filesystem storage is preferred from the evidence.
- `FILE_STORAGE_REQUIRED`: file/shared storage is required from the evidence.
- `RWO_REQUIRED`: ReadWriteOnce is inferred.
- `RWX_REQUIRED`: ReadWriteMany is inferred.
- `RAW_BLOCK_HINT`: raw-device evidence was observed.
- `RAW_BLOCK_REVIEW_REQUIRED`: raw-device evidence requires human confirmation.
- `FAST_STORAGE_RECOMMENDED`: the required performance tier is `fast`.
- `LOW_LATENCY_STORAGE_RECOMMENDED`: the required performance tier is `low_latency`.
- `STORAGE_CLASS_MATCH`: at least one supplied storage class matches.
- `NO_STORAGE_CLASS_MATCH`: no supplied storage class matches.
- `CAPACITY_RISK_LOW`: capacity risk is low.
- `CAPACITY_RISK_MEDIUM`: capacity risk is medium.
- `CAPACITY_RISK_HIGH`: capacity risk is high.
- `LATENCY_RISK_LOW`: latency risk is low.
- `LATENCY_RISK_MEDIUM`: latency risk is medium.
- `LATENCY_RISK_HIGH`: latency risk is high.
- `IOSTAT_MISSING`: iostat data is missing.
- `IOSTAT_PARSE_FAILED`: iostat data could not be parsed.
- `IOSTAT_DEVICE_MAPPING_UNCERTAIN`: mount-to-iostat device mapping was unclear.
- `PROCESS_LIST_MISSING`: process list data is missing.
- `SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE`: shared filesystem behavior was observed but no RWX file profile was supplied.
- `RAW_BLOCK_REQUIRED_NO_PROFILE`: raw Block mode was required but no Block profile was supplied.
- `CAPACITY_EXCEEDS_AVAILABLE_PROFILE`: requested size exceeds otherwise compatible profiles.
- `HUMAN_ARCHITECTURE_REVIEW_REQUIRED`: observed behavior needs human architecture review.
- `APP_DATA_PATH_DECLARED`: path-purpose metadata declared one or more application data paths.
- `FINDMNT_CONFIRMED_MOUNT`: supplemental `findmnt` evidence confirmed a candidate mount.
- `MOUNT_OPTIONS_REVIEW_REQUIRED`: mount options include behavior that needs human review.
- `BIND_MOUNT_DETECTED`: supplemental mount evidence suggests a bind mount or layered path.
- `LSBLK_DEVICE_LINEAGE_RESOLVED`: supplemental `lsblk` evidence resolved device lineage for a candidate mount.
- `INODE_PRESSURE_RISK`: supplemental inode data indicates possible inode pressure.

## Data honesty caveats

- A short iostat sample is not a benchmark.
- Process names are hints, not full application discovery.
- Root-only storage visibility reduces confidence.
- Shared filesystem detection does not explain why the app uses shared storage.
- Block-backed filesystem is not the same as raw block mode.
- Capacity headroom is a heuristic, not a sizing study.
- Evidence questions are decision aids, not automated architecture discovery.
- Policy packs encode review posture and thresholds, not application correctness.
- Declared application paths are owner evidence. If a declared path is not visible in `mount`, the tool warns rather than assuming it exists.

## Privacy and security

- Local-only.
- No telemetry.
- No network calls.
- No credentials.
- No SSH.
- No cluster access.
- No proprietary tooling required.
- Synthetic examples only.

## Proprietary and platform boundary

- The repo does not bundle, invoke, or redistribute proprietary tools.
- The repo does not include provider-specific storage-class names.
- Users supply their own command outputs and storage profile.
- Future integrations must remain optional and offline-first.

## Expansion roadmap

1. Batch mode

   Analyze many VM bundles and produce a portfolio summary:
   - number of PASS / REVIEW / FAIL workloads
   - top storage blockers
   - RWX demand count
   - fast-block demand count
   - capacity-exceeds-profile count

   This remains a pre-sales readiness view, not a migration plan.

2. Offline cluster-profile importer

   Accept a user-provided offline YAML export of storage classes.

   Do not connect to a live cluster in core.

3. Storage-questionnaire generator

   Generate a short handoff questionnaire based on blockers:
   - "What consumes /data?"
   - "Why is NFS mounted at /srv/content?"
   - "Can this app run with RWO?"
   - "Is raw block truly required?"

4. Application policy packs

   Add optional threshold packs for common workload families:
   - relational database
   - document database
   - search/logging
   - file server
   - content management

   These should only adjust thresholds and reason text.

5. Longer iostat samples

   Accept multiple iostat files or a longer time-window export.

   Still do not claim to benchmark the target platform.

6. Redacted handoff bundle

   Create a ZIP with:
   - fit JSON
   - mount report CSV
   - storage profile fingerprint
   - warning summary
   - redacted evidence

7. Markdown report

   Generate a short human-readable report for sales engineering and platform engineering handoff.

   Still no pricing, no migration wave plan, and no manifests.

8. Optional fio recommendation generator

   Do not run fio automatically.

   Generate a suggested fio test profile only when latency risk is high and the user asks for deeper validation.
