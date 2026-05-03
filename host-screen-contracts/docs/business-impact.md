# Business Impact

`host-screen-contracts` is useful because it reduces uncertainty before expensive wrapper/API work starts.

## Core Impact

- Faster discovery: recorded screen paths become contracts, fields, transitions, and replay cases.
- Better API review: OpenAPI candidates preserve screen-origin metadata.
- Less wrapper rework: drift evidence catches label, layout, field, and flow changes early.
- Safer handoff: privacy reports and tokenization help keep sensitive values local.
- Cleaner prioritization: readiness and realism reports separate quick wins from review-heavy transactions.
- Better governance: every package has warnings, blockers, evidence boundaries, and recommended next actions.

## Primary Personas

- Modernization sponsor: needs a defensible backlog and earlier delivery confidence.
- Enterprise architect: decides wrapper, API, rewrite, retire, or defer.
- API product owner: needs a candidate contract and error behavior for review.
- Host SME: verifies field meaning, hidden fields, function keys, and exception paths.
- Wrapper developer: needs implementation inputs with field origins and replay evidence.
- QA lead: needs recorded cases and drift gates.
- Security/privacy officer: needs evidence that sensitive trace values are identified before sharing.
- Partner delivery lead: needs a handoff packet before assigning implementation work.

## Measurement Model

Track these operational metrics instead of claiming automatic modernization:

- Discovery hours avoided.
- Field names accepted by SMEs versus inferred or coordinate-generated.
- Replayable cases per transaction.
- Error paths captured before implementation.
- Drift changes caught before wrapper release.
- Privacy findings removed before partner handoff.
- Bundle completeness and missing artifacts.
- Movement from synthetic evidence to approved sanitized local packages.

## Product Throughline

The product should always answer:

> Given this recorded host-screen evidence, is the transaction ready for API/wrapper review, what risks remain, and what should the team do next?
