# Policy Packs

These policy packs are generic starting points for local pilots. They use only `example.invalid` domains and should be treated as review inputs, not deployment-ready policy.

- `developer-workstation.yml`: balanced developer workstation posture for source-code-like, secret-like, and internal-identifier prompts.
- `support-team.yml`: customer-record and personal-data review posture for support drafting workflows.
- `health-data-strict.yml`: stricter handling for health-data-like and personal-data-like prompts.
- `legal-review.yml`: legal-sensitive text redirection posture with warning for lower-risk identifiers.
- `finance-strict.yml`: strict handling for financial-sensitive and credential-like prompts.
- `public-sector.yml`: conservative posture for public-record, personal-data, and internal-identifier review.
- `education.yml`: warn-mode pilot posture for low-friction training and measurement.
- `warn-only-pilot.yml`: warn-mode pilot posture that avoids hard enforcement.
- `strict-enforcement.yml`: high-interruption posture for testing hard-block behavior.

Pair focused packs with generated pilot input:

```bash
prompt-egress-guard init-pilot --pack finance-strict --output out/finance-pilot
prompt-egress-guard pilot-run \
  --policy examples/policy-packs/finance-strict.yml \
  --input out/finance-pilot/input \
  --output out/finance-pilot/run
```

Before real deployment, replace domains and selectors with tested site profiles and review the generated policy explanation.
