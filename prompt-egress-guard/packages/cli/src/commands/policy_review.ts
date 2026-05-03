import fs from "node:fs";
import { loadPolicyFile, type Action, type Policy } from "@prompt-egress-guard/core";

export async function explainPolicyCommand(args: Record<string, string | boolean>): Promise<number> {
  const policyPath = String(args.policy ?? "");
  const output = typeof args.output === "string" ? args.output : undefined;
  if (!policyPath) {
    console.error("missing --policy");
    return 1;
  }
  const result = loadPolicyFile(policyPath);
  if (!result.valid || !result.policy) {
    console.error(result.blockers.join("\n"));
    return 1;
  }
  const explanation = explainPolicy(result.policy, result.warnings);
  const text = `${JSON.stringify(explanation, null, 2)}\n`;
  if (output) fs.writeFileSync(output, text);
  else console.log(text.trimEnd());
  return 0;
}

export async function diffPolicyCommand(args: Record<string, string | boolean>): Promise<number> {
  const basePath = String(args.base ?? "");
  const candidatePath = String(args.candidate ?? "");
  const output = typeof args.output === "string" ? args.output : undefined;
  if (!basePath || !candidatePath) {
    console.error("missing --base or --candidate");
    return 1;
  }
  const base = loadPolicyFile(basePath);
  const candidate = loadPolicyFile(candidatePath);
  if (!base.valid || !base.policy || !candidate.valid || !candidate.policy) {
    console.error([...base.blockers, ...candidate.blockers].join("\n"));
    return 1;
  }
  const diff = diffPolicies(base.policy, candidate.policy);
  const text = `${JSON.stringify(diff, null, 2)}\n`;
  if (output) fs.writeFileSync(output, text);
  else console.log(text.trimEnd());
  return 0;
}

export function explainPolicy(policy: Policy, validationWarnings: string[] = []): Record<string, unknown> {
  const categoryActions = Object.entries(policy.actions.category_actions).sort(([a], [b]) => a.localeCompare(b));
  return {
    policy_id: policy.policy_id,
    mode: policy.mode,
    monitored_site_count: policy.monitored_sites.length,
    host_permissions: [...new Set(policy.monitored_sites.flatMap((site) => site.host_permissions))].sort(),
    action_thresholds: policy.actions.thresholds,
    category_actions: Object.fromEntries(categoryActions),
    approved_destination_configured: Boolean(policy.approved_destination?.url),
    approved_destination_includes_prompt: Boolean(policy.approved_destination?.include_prompt),
    clipboard_copy_allowed: Boolean(policy.approved_destination?.clipboard_copy_allowed),
    raw_prompt_storage_enabled: policy.audit.store_raw_prompt,
    redacted_excerpt_enabled: policy.audit.store_redacted_excerpt,
    dnr_enabled: policy.dnr.enabled,
    likely_business_effect: businessEffect(policy),
    warnings: validationWarnings
  };
}

export function diffPolicies(base: Policy, candidate: Policy): Record<string, unknown> {
  return {
    base_policy_id: base.policy_id,
    candidate_policy_id: candidate.policy_id,
    mode_changed: base.mode !== candidate.mode ? { from: base.mode, to: candidate.mode } : null,
    site_count_changed: base.monitored_sites.length !== candidate.monitored_sites.length ? { from: base.monitored_sites.length, to: candidate.monitored_sites.length } : null,
    threshold_changes: diffObject(base.actions.thresholds, candidate.actions.thresholds),
    category_action_changes: diffObject(base.actions.category_actions, candidate.actions.category_actions),
    audit_changes: diffObject(base.audit, candidate.audit),
    approved_destination_changes: diffObject(base.approved_destination ?? {}, candidate.approved_destination ?? {}),
    review_summary: reviewSummary(base, candidate)
  };
}

function businessEffect(policy: Policy): string {
  const counts = Object.values(policy.actions.category_actions).reduce((acc, action) => {
    acc[action] = (acc[action] ?? 0) + 1;
    return acc;
  }, {} as Record<Action, number>);
  return `Configured policy blocks ${counts.BLOCK ?? 0} detector families, redirects ${counts.REDIRECT ?? 0}, warns ${counts.WARN ?? 0}, and allows ${counts.ALLOW ?? 0}.`;
}

function diffObject(base: Record<string, unknown>, candidate: Record<string, unknown>): Record<string, { from: unknown; to: unknown }> {
  const keys = [...new Set([...Object.keys(base), ...Object.keys(candidate)])].sort();
  return Object.fromEntries(keys.filter((key) => JSON.stringify(base[key]) !== JSON.stringify(candidate[key])).map((key) => [key, { from: base[key], to: candidate[key] }]));
}

function reviewSummary(base: Policy, candidate: Policy): string {
  const changes = Object.keys(diffObject(base.actions.category_actions, candidate.actions.category_actions)).length;
  const mode = base.mode === candidate.mode ? "same policy mode" : `mode changes from ${base.mode} to ${candidate.mode}`;
  return `Policy diff has ${changes} category-action changes and ${mode}. Review whether this changes user interruption, block rate, or approved-endpoint handoff volume.`;
}
