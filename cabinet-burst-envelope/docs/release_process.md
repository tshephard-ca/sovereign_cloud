# Release Process

This project is offline-first and vendor-neutral. Release preparation must not require live data-centre systems, credentials, telemetry agents, or external service calls.

Local release checklist:

1. Run tests:

   ```bash
   python -m pytest -q
   ```

2. Run synthetic benchmark:

   ```bash
   cabinet-burst-envelope benchmark --output-dir out/benchmark
   ```

3. Generate release fingerprints and an SPDX-style file inventory:

   ```bash
   cabinet-burst-envelope release-report --repo-root . --output-dir out/release
   ```

4. Review generated files:

   - `artifact_fingerprints.json`
   - `sbom.spdx.json`
   - `release_checklist.md`

5. Sign release artifacts using the maintainer-approved offline signing process.

6. Confirm the release contains no credentials, raw proprietary exports, live collectors, or device integrations.
