# Contributing

`estate-triage` is a deterministic, local-only triage engine. Contributions should preserve data honesty, explainability, and no-external-service behavior.

## Development

```bash
python3 -m pip install -e ".[test]"
python3 -m pytest -q
```

## Pull Request Checklist

- Add or update tests for behavior changes.
- Keep examples synthetic.
- Do not add proprietary SDKs, API clients, credentials, telemetry, pricing estimates, or migration planning.
- Do not include real customer, provider, reseller, or consulting-company names.
- Update docs when public CLI, schema, policy, or workflow behavior changes.

## Policy Changes

Policy changes should include:

- policy version update when behavior changes materially
- `policy-impact` output against a representative assessment artifact
- corpus regression result through `test-policy`
- approval metadata in the policy pack
