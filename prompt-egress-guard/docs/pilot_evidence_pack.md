# Pilot Evidence Pack

The pilot evidence pack is the main business artifact. It is designed for a security, platform, or administrator review meeting where the question is whether the configured prompt guard behavior is clear enough to pilot with users.

## Flow

1. Generate synthetic input data:

   ```bash
   prompt-egress-guard init-pilot --pack developer-workstation --output out/pilot
   ```

2. Validate the generated corpus against a policy:

   ```bash
   prompt-egress-guard validate-corpus \
     --input out/pilot/input \
     --policy examples/policies/default-policy.yml
   ```

3. Run the local pilot:

   ```bash
   prompt-egress-guard pilot-run \
     --policy examples/policies/default-policy.yml \
     --input out/pilot/input \
     --output out/pilot/run
   ```

4. Write the decision packet:

   ```bash
   prompt-egress-guard pilot-report \
     --policy examples/policies/default-policy.yml \
     --input out/pilot/input \
     --run out/pilot/run \
     --output out/pilot/decision_packet
   ```

## Input Artifacts

- `prompt_corpus.jsonl`: deterministic synthetic prompt records.
- `prompts/*.txt`: individual synthetic prompts.
- `dom_scenarios.json`: DOM element and submit-path coverage.
- `policy_modes.json`: policy mode coverage.
- `unsafe_policy_cases.json`: invalid or unsafe policy examples.
- `business_context.json`: workflow labels and expected business outcomes.

## Run Artifacts

- `scan_results.json`: local detector and policy decisions for every prompt.
- `scan-results/*.json`: per-prompt scan result files.
- `local_audit.jsonl`: local audit events for non-allow decisions.
- `audit_summary.json`: deterministic redacted audit summary.
- `business_impact_report.json`: grouped business findings.
- `extension/manifest.json`: generated host permissions and extension metadata.
- `extension/site_policy.json`: browser-consumable policy config.
- `extension/dnr_rules.json`: empty by default unless DNR is explicitly enabled.
- `pilot_assessment.json`: machine-readable evidence coverage and gaps.
- `pilot_summary.md`: human-readable review summary.

## Decision Packet

The decision packet contains:

- `pilot_summary.md`
- `pilot_assessment.json`
- `manifest.json` with deterministic input and run hashes

Review the packet for:

- expected versus actual action mismatches
- raw secret absence in outputs
- redacted excerpt availability
- prompt hash availability
- extension host-permission scope
- DNR mode clarity
- input and output coverage gaps
- admin questions generated from findings

## Business Impact Throughline

The packet should make these tradeoffs concrete:

- Which workflows are stopped outright?
- Which workflows are steered to an approved endpoint handoff?
- Which workflows only warn the user?
- Which safe controls remain allowed?
- Which selectors or policy settings need ownership?
- Which policy changes would increase user friction?

The output is review-only. It does not prove production coverage, compliance, or user adoption.
