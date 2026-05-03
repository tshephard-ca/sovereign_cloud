# Policy Authoring

Policies define monitored sites, selectors, thresholds, category actions, approved endpoint handoff behavior, audit storage, scanner settings, user experience, and optional domain-scope DNR behavior.

Use narrow host permissions and tested selectors. Avoid `<all_urls>` unless explicitly acknowledged for a controlled deployment. Keep `dnr.enabled=false` for content-inspection pilots unless the intent is domain-scope blocking or redirect without prompt inspection.

Use the review commands before rollout:

```bash
prompt-egress-guard explain-policy --policy examples/policies/default-policy.yml
prompt-egress-guard diff-policy \
  --base examples/policies/default-policy.yml \
  --candidate examples/policy-packs/strict-enforcement.yml
```

Decision fields separate detection from enforcement:

- `detected_risk_level` describes the matched prompt risk.
- `base_action_from_score` describes threshold behavior.
- `strongest_category_action` describes category-specific policy behavior.
- `final_action` describes the action after policy mode is applied.
- `allowed_user_actions` describes what the overlay can offer.

Admin questions:

- `PROMPT_INPUT_NOT_FOUND`: Do the configured selectors still match the target public-AI page?
- `SOURCE_CODE_PATTERN_DETECTED`: Should developers be redirected to an approved coding assistant endpoint?
- `HEALTH_RECORD_PATTERN_DETECTED`: Should health-data-like prompts be blocked outright or redirected to a specialized approved endpoint?
- `LEGAL_PRIVILEGE_PATTERN_DETECTED`: Should legal-sensitive text be redirected, blocked, or require acknowledgement?
- `CUSTOMER_RECORD_PATTERN_DETECTED`: Which customer identifiers should trigger redirect versus warn?
- `APPROVED_DESTINATION_MISSING`: What approved AI destination should users be sent to when policy triggers redirect?
- `CLIPBOARD_COPY_ALLOWED_BY_POLICY`: Is explicit clipboard copy acceptable, or should prompt transfer be disabled entirely?
- `SITE_SELECTOR_MAY_BE_STALE`: Who owns selector maintenance for this configured public-AI site?
