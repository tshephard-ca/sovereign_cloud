# Governance

The project is maintained as a small open-source CLI and kernel. Maintainers are responsible for preserving the core constraints:

- deterministic local execution
- no external service calls
- no credentials
- synthetic examples only
- explainable evidence, identity, feature, and policy traces

## Decision Records

Significant changes to schemas, policy semantics, ranking behavior, privacy behavior, or bundle layout should be documented in `docs/architecture.md` or a dedicated architecture note.

## Compatibility

Public schemas carry version constants. Compatibility can be inspected with:

```bash
estate-triage schema --kind compatibility
```

Breaking schema changes should update the relevant schema version and include migration notes.
