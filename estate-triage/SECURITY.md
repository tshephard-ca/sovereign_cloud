# Security Policy

`estate-triage` is designed to run locally without credentials or external calls.

## Reporting

Report security issues privately to the project maintainers for the environment where this repository is hosted. Do not include real customer data in reports.

## Local Privacy Checks

Before sharing generated artifacts, run:

```bash
estate-triage privacy-scan --path outputs --needle "sensitive-string"
```

Use redaction for assessment and bundle outputs when artifacts may leave the local assessment environment.
