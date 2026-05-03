# Redaction Contract

Case bundles are designed for sharing redacted compatibility evidence, not raw logs.

The redaction gate checks for:

- raw bucket names known during bundle creation
- object-key templates that expose literal path names
- account IDs
- IP addresses
- ARNs
- unredacted endpoint hostnames
- presigned signature or credential query values
- access-key-like tokens
- real provider names

The bundle contains `redaction-report.json`:

```json
{
  "redaction_status": "PASS",
  "shareable": true,
  "checks": {
    "raw_bucket_names_found": 0,
    "ip_addresses_found": 0,
    "presigned_signatures_found": 0
  }
}
```

Use `bundle validate --strict-redaction` before importing into a corpus or sharing externally.
