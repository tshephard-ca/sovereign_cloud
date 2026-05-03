# Admin Review Checklist

Use this checklist before moving from a local pilot to a managed-browser pilot.

## Policy Scope

- Confirm every `monitored_sites` entry is intended.
- Confirm every host permission is narrow and avoids `<all_urls>`.
- Confirm selectors were tested on the intended pages.
- Confirm keyboard submit behavior matches user workflows.
- Confirm `dnr.enabled` is false unless domain-scope blocking is intentional.

## Decision Behavior

- Review `base_action_from_score`, `strongest_category_action`, and `final_action` for representative prompts.
- Confirm `WARN` cases can continue only where acceptable.
- Confirm `REDIRECT` cases have a useful approved endpoint handoff.
- Confirm `BLOCK` cases have a documented alternate workflow.
- Confirm observe-mode or warn-mode pilots are clearly labeled.

## Privacy And Audit

- Confirm `approved_destination.include_prompt=false` unless explicitly approved.
- Confirm `audit.store_raw_prompt=false` unless explicitly approved.
- Confirm redacted excerpts are sufficient for user explanation.
- Confirm prompt hashes are sufficient for local correlation.
- Confirm audit retention fits the pilot goal.

## Evidence Packet

- Review `pilot_summary.md` with the policy owner.
- Review all input and output gaps in `pilot_assessment.json`.
- Confirm raw synthetic secrets are absent from scan and audit outputs.
- Confirm negative controls stayed allowed.
- Confirm action-path coverage includes allow, warn, redirect, and block for broad packs.
- Confirm focused packs are not mistaken for full detector coverage.

## Rollout Questions

- Who owns selector maintenance when public-AI pages change?
- Which teams need approved endpoint handoff?
- Which categories should block instead of redirect or warn?
- Which categories are too noisy for hard enforcement?
- What user-support path exists after a block?
- What review process approves policy changes?

The checklist supports review. It is not an attestation or deployment approval by itself.
