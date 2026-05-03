# Deployment Notes

Build the extension after policy validation:

```bash
prompt-egress-guard validate-policy \
  --policy examples/policies/default-policy.yml

prompt-egress-guard compile-extension \
  --policy examples/policies/default-policy.yml \
  --output-dir dist/extension
```

Review generated `manifest.json`, host permissions, `site_policy.json`, `dnr_rules.json`, `content_script.js`, and `service_worker.js` before deployment.

Default deployment posture is content-script-first. `dnr.enabled` is false by default because declarative network rules cannot inspect prompt content. If a policy enables DNR, treat those rules as domain-scope blocking or redirect artifacts only, and review the `DNR_CONTENT_INSPECTION_NOT_AVAILABLE` warning.

Recommended pilot flow:

```bash
prompt-egress-guard init-pilot --pack developer-workstation --output out/pilot
prompt-egress-guard pilot-run \
  --policy examples/policies/default-policy.yml \
  --input out/pilot/input \
  --output out/pilot/run
prompt-egress-guard pilot-report \
  --policy examples/policies/default-policy.yml \
  --input out/pilot/input \
  --run out/pilot/run \
  --output out/pilot/decision_packet
```

Review the pilot summary before extension deployment. A passing pilot means generated evidence is internally consistent. It does not prove production coverage.

This repository does not sign, publish, install, or centrally manage an extension. Use your browser administration process if deploying to managed browsers.
