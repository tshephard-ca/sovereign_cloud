# Release Process

1. Run `python3 -m pytest -q`.
2. Run `estate-triage schema --kind compatibility`.
3. Run generated bundle analysis and `workflow-pack` on synthetic coverage data.
4. Run `privacy-scan` on shareable artifacts.
5. Update version metadata in `pyproject.toml`.
6. Record policy changes with `policy-impact` and corpus regression results.
7. Publish source and wheel artifacts from a clean checkout.

The project does not require external services at runtime. Release automation may use repository hosting infrastructure, but the CLI itself must remain local-only.
