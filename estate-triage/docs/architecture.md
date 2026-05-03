# estate-triage Core Architecture

`estate-triage` is structured as a deterministic assessment kernel plus a presentation layer. The kernel creates auditable facts. The presentation layer turns those facts into a discovery work plan.

## Pipeline

```text
source export
  -> adapter
  -> EvidenceSet
  -> identity resolver
  -> feature registry
  -> policy engine
  -> AssessmentResult
  -> presentation/workflow layer
  -> renderer
```

Business mapping:

- adapters create input readiness and provenance
- identity resolution creates workload trust status
- feature registry creates evidence signals
- policy engine creates motion fit
- ranking creates queue shape
- presentation layer creates next steps, questions, and data requests
- renderers create CSV, JSON, and Markdown artifacts

## Stable Contracts

Current contract versions:

- evidence schema: `1.0.0`
- feature schema: `1.0.0`
- policy schema: `1.0.0`
- assessment schema: `1.0.0`
- trace schema: `1.0.0`

Schema versions are declared in `estate_triage.evidence`.

## Adapter Boundary

Adapters are allowed to:

- parse source files
- map source columns to canonical evidence fields
- normalize units and dates
- emit data-quality findings
- preserve source provenance

Adapters are not allowed to:

- score workloads
- assign sales motions
- infer business criticality
- hide identity conflicts
- call external services

## Evidence Model

Every `EvidenceField` carries:

- canonical field name
- normalized value
- raw value
- unit
- source type
- source path
- source row
- source column
- parser name
- confidence
- parse warnings

This makes downstream findings auditable back to source rows.

## Identity Resolution

Identity resolution emits explicit states:

- `RESOLVED`
- `PROBABLE`
- `CONFLICTED`
- `DUPLICATE_CANDIDATES`
- `UNMATCHED`

UUID matches are preferred over name matches. When UUID and name disagree, the workload is marked `CONFLICTED`; the UUID match is used for deterministic output, and the conflict is included in data-quality findings.

## Feature Registry

Feature calculators are registered in `estate_triage.feature_engine`.

Each feature emits:

- name
- version
- value
- required evidence
- optional evidence
- missing evidence
- source references
- confidence impact
- trace text

Policies consume feature values. They should not duplicate feature-calculation logic.

## Policy Engine

The default policy pack is `default@1.0.0`.

The policy model is intentionally small:

- conditions
- boolean groups
- threshold comparisons
- score contributions
- reason codes
- blocking flags
- rule traces

Policies do not execute arbitrary code.

## Assessment Result

`AssessmentResult` is the primary kernel output. It contains:

- input counts
- policy version
- workload assessments
- identity traces
- feature traces
- rule traces
- missing-evidence requests
- blocking flags
- data-quality findings

CSV output is rendered from this structure for compatibility. Workflow artifacts are also rendered from this structure, but they are intentionally less technical.

## Presentation Layer

The presentation layer lives in `estate_triage.business_impact` and `estate_triage.workflow`.

It adds:

- `presentation_class`
- `evidence_strength`
- `owner_persona`
- `recommended_next_step`
- `business_question`
- `why_this_matters`
- `do_not_present_reason`
- aggregated data-request checklists

This layer must not rescore workloads or hide kernel evidence. Its job is to make the result usable in a business conversation while preserving links to the technical trace.

## Ranking

Ranking is separate from scoring. Supported modes:

- `global`
- `balanced`
- `per_motion`
- `confidence_first`
- `blockers_first`
- `missing_evidence_first`

This lets the same assessment support different workflows without changing rules.

## Privacy

Redaction is applied at render time. CSV and assessment JSON redaction replace workload names and hash workload keys/UUID evidence. Raw input files are never embedded in output by default.

## Extension Priorities

The next extensions should preserve the kernel boundary:

1. Add schema migration helpers for future contract versions.
2. Expand the golden corpus with messy identity, data-quality, and presentation-class cases.
3. Add stronger identity context from host, cluster, datacenter, and historical names.
4. Add policy-pack regression assertions against expected workflow outcomes.
5. Add workbook ingestion as an adapter outside the core policy engine.
