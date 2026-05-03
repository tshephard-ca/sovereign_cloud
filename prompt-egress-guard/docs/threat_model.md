# Threat Model

The protected behavior is narrow: a user typing or pasting a risky prompt candidate into a configured public-AI web page.

In scope:

- Configured public-AI host patterns.
- DOM-level prompt boxes selected by policy.
- Local deterministic sensitive-pattern matching before submit.
- Block, warn, or redirect handoff decisions.
- Redacted local audit summary.

Out of scope:

- Native apps, mobile apps, API clients, private browsing, unmanaged browsers, and unconfigured sites.
- Network-body inspection.
- TLS interception.
- Response capture.
- File and screenshot capture.
- Full DLP or traffic-wide coverage.

Main risks:

- Site DOM changes can make selectors stale.
- Regex detectors can false-positive or false-negative.
- Users can move content through channels the extension does not cover.
- Approved endpoints are user configured and not verified by this tool.
