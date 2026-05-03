# Pilot Packs

Pilot packs generate deterministic synthetic prompt corpora for review-only evidence runs. They are not production data and should not contain secrets, customer records, health data, financial data, or proprietary content.

Available generated packs:

- `developer-workstation`
- `support-team`
- `health-data-strict`
- `legal-review`
- `finance-strict`
- `public-sector`
- `education`
- `warn-only-pilot`
- `strict-enforcement`

Generate a complete input bundle with:

```bash
prompt-egress-guard init-pilot --pack developer-workstation --output out/pilot
```

The bundle includes `prompt_corpus.jsonl`, individual prompt text files, DOM scenarios, policy-mode variants, unsafe-policy cases, and business context.
