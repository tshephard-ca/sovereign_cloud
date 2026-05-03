# prompt-egress-guard

`prompt-egress-guard` is a local-first prompt egress pilot and browser-extension core for configured public-AI sites. It scans prompt text in the browser before submission, applies deterministic policy rules, and produces review-only evidence about whether risky prompt candidates are allowed, warned, redirected, or blocked.

The narrow business question is:

> For configured public-AI sites, which prompt workflows create egress risk, what policy action fires, and what should administrators change before a managed rollout?

## What The Project Does

- Runs deterministic local detectors for secret-like, source-code-like, customer-record-like, health-data-like, legal-sensitive, internal-identifier, personal-data-like, and financial-sensitive prompt patterns.
- Applies a policy decision model with `ALLOW`, `WARN`, `REDIRECT`, and `BLOCK`.
- Separates detected risk, score-based action, category action, final policy action, and allowed user actions in scan output.
- Compiles a Manifest V3 browser extension for explicitly configured host permissions.
- Generates synthetic pilot input data, local scan outputs, redacted audit summaries, extension artifacts, and a review-only decision packet.
- Provides policy explanation and policy diff commands for administrator review.

## What The Project Does Not Do

It does not replace full DLP, endpoint security, network security, compliance review, browser management, model gateways, or AI governance programs. It does not inspect all AI traffic, intercept TLS, call an LLM, call external classifiers, capture files, capture screenshots, capture model responses, manage credentials, or route production traffic.

## Why This Exists

Teams often discover prompt-egress risk through anecdotes: a secret pasted into a chat page, source code copied into a public assistant, or customer context sent to an unapproved destination. This project turns that vague concern into a concrete pilot packet:

- generated synthetic prompt workflows
- declared policy behavior
- local detector results
- extension host-permission artifacts
- redacted audit summary
- business-impact findings
- admin follow-up questions

The output is meant for review and rollout planning. It is not compliance proof.

## Quickstart

```bash
npm install
npm run build
npm test
```

Use the built CLI locally:

```bash
CLI="node packages/cli/dist/index.js"
```

Validate and explain a policy:

```bash
$CLI validate-policy --policy examples/policies/default-policy.yml
$CLI explain-policy --policy examples/policies/default-policy.yml --output out/policy_explanation.json
```

Run a complete pilot evidence workflow:

```bash
$CLI init-pilot \
  --pack developer-workstation \
  --output out/developer-pilot

$CLI validate-corpus \
  --input out/developer-pilot/input \
  --policy examples/policies/default-policy.yml

$CLI pilot-run \
  --policy examples/policies/default-policy.yml \
  --input out/developer-pilot/input \
  --output out/developer-pilot/run

$CLI pilot-report \
  --policy examples/policies/default-policy.yml \
  --input out/developer-pilot/input \
  --run out/developer-pilot/run \
  --output out/developer-pilot/decision_packet
```

The key review outputs are:

- `out/developer-pilot/input/prompt_corpus.jsonl`
- `out/developer-pilot/input/dom_scenarios.json`
- `out/developer-pilot/run/scan_results.json`
- `out/developer-pilot/run/audit_summary.json`
- `out/developer-pilot/run/business_impact_report.json`
- `out/developer-pilot/run/extension/manifest.json`
- `out/developer-pilot/run/extension/site_policy.json`
- `out/developer-pilot/run/pilot_assessment.json`
- `out/developer-pilot/run/pilot_summary.md`
- `out/developer-pilot/decision_packet/pilot_summary.md`

Legacy `real-world-*` commands are retained as compatibility aliases. New usage should prefer `init-pilot`, `pilot-run`, and `pilot-report`.

## Generated Input Data

`init-pilot` creates all pilot inputs needed for a review-only run:

- `prompt_corpus.jsonl`: deterministic synthetic prompt records with expected actions.
- `prompts/*.txt`: one prompt file per record.
- `dom_scenarios.json`: prompt element and submit-path coverage.
- `policy_modes.json`: observe, warn, and enforce mode coverage.
- `unsafe_policy_cases.json`: validation cases for unsafe prompt transfer, raw audit storage, and broad host permissions.
- `business_context.json`: workflow labels used in the business-impact report.

Available pilot packs:

- `developer-workstation`
- `support-team`
- `health-data-strict`
- `legal-review`
- `finance-strict`
- `public-sector`
- `education`
- `warn-only-pilot`
- `strict-enforcement`

Synthetic prompts are intentionally boring. They must not contain production secrets, personal data, health data, financial data, customer records, or proprietary content.

## Policy Authoring

Policies define:

- monitored sites and host permissions
- prompt selectors and submit selectors
- keyboard submit behavior
- action thresholds
- category-specific actions
- approved endpoint handoff settings
- local audit settings
- scanner limits
- user-experience options
- optional declarative network rule posture

Examples use only `example.invalid` domains. Real deployments require user-supplied domains, selectors, approved destinations, and review by the policy owner.

Unsafe settings fail validation unless explicitly acknowledged:

- `approved_destination.include_prompt=true`
- `audit.store_raw_prompt=true`
- `<all_urls>` host permissions

## Policy Packs

Policy packs live in `examples/policy-packs/` and provide generic starting points for review:

- developer workstation
- support team
- health-data strict
- legal review
- finance strict
- public sector
- education
- warn-only pilot
- strict enforcement

They are not deployment-ready defaults. Use `explain-policy` and `diff-policy` to make action changes reviewable:

```bash
$CLI diff-policy \
  --base examples/policies/default-policy.yml \
  --candidate examples/policy-packs/strict-enforcement.yml \
  --output out/policy_diff.json
```

## Decision Output

Each scan result includes both compatibility and clearer decision fields:

- `action`: final policy action, retained for existing consumers.
- `risk_status`: compatibility alias for `action`.
- `detected_risk_level`: `NONE`, `LOW`, `MEDIUM`, or `HIGH`.
- `base_action_from_score`: action derived from aggregate score thresholds.
- `strongest_category_action`: strongest action required by matched detector categories.
- `final_action`: final action after policy mode is applied.
- `policy_mode`: `observe`, `warn`, or `enforce`.
- `allowed_user_actions`: submit, continue, cancel, or approved-destination options.
- `decision_summary`: plain-language reason for the final action.

This separation makes review easier. A prompt can be high-risk by detection but still produce `WARN` in warn-mode or `ALLOW` in observe-mode.

## Output Interpretation

- `ALLOW`: no configured rule triggered above policy thresholds, or no prompt was captured in a negative-control scenario.
- `WARN`: a risky prompt candidate requires user review before continuing.
- `REDIRECT`: the configured public-AI submission is stopped and an approved endpoint handoff is offered.
- `BLOCK`: the configured public-AI submission is stopped.

None of these mean complete protection, compliance proof, or production readiness.

## Browser-Extension Reality

The extension uses content scripts to inspect configured page DOM inputs before configured submit paths. Coverage is limited to pages matched by the policy host permissions and selectors.

Declarative network rules are disabled by default because they can block or redirect domains but cannot inspect prompt content. If `dnr.enabled=true`, generated DNR rules are domain-scope artifacts only and the policy validator emits `DNR_CONTENT_INSPECTION_NOT_AVAILABLE`.

Native apps, mobile apps, API clients, private browsing, unmanaged browsers, unconfigured sites, and copy/paste into other channels are out of scope.

## Redaction And Audit

Raw prompts are not stored by default. Outputs use prompt hashes and redacted excerpts. The audit path is local-only and review-only. There is no telemetry.

If raw prompt storage or prompt-in-handoff is enabled with acknowledgement, treat the policy as unsafe until a policy owner explicitly approves the risk.

## Privacy And Security

- No external classifier calls.
- No LLM calls.
- No telemetry.
- No credential storage.
- No file capture.
- No screenshot capture.
- No model response capture.
- No TLS interception.
- No raw prompt storage by default.
- Narrow host permissions in examples.

## Review Packet

The pilot summary answers:

- Which workflows were exercised?
- Which risky prompt candidates were blocked, redirected, or warned?
- Which safe and negative-control cases stayed allowed?
- Did generated inputs cover detector categories, action paths, DOM inputs, submit paths, and policy modes?
- Did outputs include scan results, audit summaries, extension artifacts, redaction evidence, and deterministic ordering?
- What admin questions should be resolved before rollout?

See `docs/pilot_evidence_pack.md` and `docs/admin_review_checklist.md` for the review workflow.

## Caveats

1. DOM-level inspection covers configured web pages only.
2. Browser extensions cannot reliably monitor all AI use.
3. Native apps, mobile apps, API clients, private browsing, unmanaged browsers, and unconfigured sites are out of scope.
4. Public-AI sites change their DOM; selectors may become stale.
5. Pattern matching can false-positive and false-negative.
6. A warning, redirect, or block does not prove compliance.
7. An approved endpoint is user-configured; this tool does not verify its controls.
8. No prompt text is sent to a classifier.
9. The extension does not inspect model responses.
10. The extension does not prevent copy/paste into other channels.

## Reason Codes

Reason codes are deterministic and intended for local audit, overlay display, policy tests, and pilot reports. See `docs/reason_codes.md` for the dictionary and review guidance.

## Roadmap

1. Selector-pack plugin system for optional user-maintained selector packs.
2. Managed-browser deployment guidance.
3. Native messaging local classifier for larger policies and local audit export.
4. Approved-endpoint handoff adapters without auto-submit by default.
5. Team trend reports over redacted local audit exports.
6. Redacted decision bundle with policy hash, extension config, audit summary, reason-code counts, and no raw prompts.
7. Optional response-side guard as a separate module.
8. Model-gateway integration remains explicitly out of scope for core.
