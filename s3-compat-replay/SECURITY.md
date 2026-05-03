# Security

This project is local-first. It has no telemetry and does not contact external services during analysis.

Security expectations:

- Do not paste credentials into command lines or issue reports.
- `probe` reads credentials only from explicitly named environment variables.
- Do not contribute raw logs.
- Do not contribute endpoint URLs.
- Do not contribute customer names or provider names.
- Validate case bundles with strict redaction before sharing.

Report security issues privately through the repository maintainer process. Do not publish sensitive logs or probe output in public issues.
