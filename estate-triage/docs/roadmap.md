# Roadmap And Known Boundaries

This roadmap replaces the older working gap registers as the public planning surface. Historical gap notes may exist in archived documents, but this page is the clean current view.

## Near-Term Enhancements

1. Field-calibrated generator profiles
   - Use sanitized real-export shape statistics to tune synthetic estate mixes.
   - Keep synthetic coverage profiles separate from field-derived calibration.

2. Stronger workflow handoff
   - Add optional owner-group, application, and environment fields when supplied by users.
   - Keep the kernel independent of any one inventory system.

3. Policy regression corpus
   - Expand corpus expectations to include selected feature values and workflow presentation classes.
   - Preserve redaction while retaining numeric evidence needed for policy replay.

4. Input mapping UX
   - Improve mapping review output for non-standard CSV exports.
   - Keep CSV as the core input boundary.

5. Business feedback loop
   - Track whether findings were accepted, rejected, needed more data, or became follow-up work.
   - Use feedback for policy calibration, not automated business-criticality inference.

## Longer-Term Options

1. Optional adapter packages for common export shapes.
2. Optional workbook ingestion for multi-sheet local files.
3. Richer handoff bundles with redacted worklists, evidence packets, and policy fingerprints.
4. Policy presets for different estate patterns.
5. Better source-window and stale-export diagnostics.

## Boundaries

`estate-triage` should remain:

- local-first
- deterministic
- source-export based
- auditable
- explicit about missing evidence

It should not become:

- a migration orchestrator
- a pricing engine
- a backup verifier
- a source-platform API client
- a proprietary SDK wrapper
- an application dependency mapper
- a performance benchmark

## Data Honesty

The strongest product claim is modest: the tool can turn incomplete local evidence into a clearer triage conversation. That is enough. It should not imply that a workload is ready to move, safe to archive, safe to resize, or recoverable without human validation.
