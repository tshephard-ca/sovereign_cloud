import fs from "node:fs";
import yaml from "js-yaml";
import { PolicySchema, type Policy, type ValidationResult } from "./models.js";

const hostPattern = /^(https?:\/\/|\*:\/\/)(\*\.)?([a-z0-9-]+|\*)\.[a-z0-9.-]+(?::\d+)?\/.*$/i;
const localhostPattern = /^http:\/\/localhost(?::\d+)?\/.*$/i;
const allUrls = "<all_urls>";

export function loadPolicyFile(path: string): ValidationResult {
  try {
    const parsed = yaml.load(fs.readFileSync(path, "utf8"));
    return validatePolicy(parsed);
  } catch (error) {
    return {
      valid: false,
      warnings: [],
      blockers: [`POLICY_INVALID: ${(error as Error).message}`]
    };
  }
}

export function validatePolicy(input: unknown): ValidationResult {
  const warnings: string[] = [];
  const blockers: string[] = [];
  const parsed = PolicySchema.safeParse(input);
  if (!parsed.success) {
    return { valid: false, warnings, blockers: [`POLICY_INVALID: ${parsed.error.message}`] };
  }
  const policy = parsed.data;
  if (policy.monitored_sites.length === 0) blockers.push("MONITORED_SITE_MISSING");
  for (const site of policy.monitored_sites) {
    for (const permission of site.host_permissions) {
      if (permission === allUrls) {
        warnings.push("BROAD_HOST_PERMISSION_REQUESTED");
        if (!policy.unsafe_broad_host_permissions_acknowledgement) blockers.push("UNSAFE_BROAD_HOST_PERMISSIONS_WITHOUT_ACK");
      } else if (!hostPattern.test(permission) && !localhostPattern.test(permission)) {
        blockers.push(`HOST_PERMISSION_INVALID: ${permission}`);
      }
    }
  }
  const thresholds = policy.actions.thresholds;
  if (!(thresholds.block_score > thresholds.redirect_score && thresholds.redirect_score > thresholds.warn_score)) {
    blockers.push("THRESHOLDS_INVALID");
  }
  if (policy.approved_destination) {
    const urlResult = validateApprovedUrl(policy.approved_destination.url);
    if (!urlResult.valid) blockers.push(`APPROVED_DESTINATION_INVALID: ${policy.approved_destination.url}`);
    if (policy.approved_destination.include_prompt && !policy.approved_destination.unsafe_prompt_transfer_acknowledgement) {
      blockers.push("UNSAFE_PROMPT_TRANSFER_WITHOUT_ACK");
    }
    if (policy.approved_destination.clipboard_copy_allowed) warnings.push("CLIPBOARD_COPY_ALLOWED_BY_POLICY");
  }
  if (policy.dnr.enabled) warnings.push("DNR_CONTENT_INSPECTION_NOT_AVAILABLE");
  if (policy.audit.store_raw_prompt && !policy.audit.unsafe_audit_storage_acknowledgement) {
    blockers.push("RAW_PROMPT_STORAGE_WITHOUT_ACK");
  }
  if (!policy.audit.store_raw_prompt) warnings.push("RAW_PROMPT_STORAGE_DISABLED");
  if (policy.audit.store_redacted_excerpt) warnings.push("REDACTION_ENABLED");
  return { valid: blockers.length === 0, policy, warnings: [...new Set(warnings)], blockers: [...new Set(blockers)] };
}

export function assertValidPolicy(input: unknown): Policy {
  const result = validatePolicy(input);
  if (!result.valid || !result.policy) {
    throw new Error(result.blockers.join("; ") || "POLICY_INVALID");
  }
  return result.policy;
}

export function validateApprovedUrl(value: string): { valid: boolean; reason?: string } {
  try {
    const url = new URL(value);
    if (url.protocol === "https:") return { valid: true };
    if (url.hostname === "localhost" || url.hostname.endsWith(".invalid")) return { valid: true };
    return { valid: false, reason: "approved destination must be HTTPS unless localhost or .invalid" };
  } catch {
    return { valid: false, reason: "invalid URL" };
  }
}

export function policyForSite(policy: Policy, siteId: string): Policy["monitored_sites"][number] | undefined {
  return policy.monitored_sites.find((site) => site.site_id === siteId);
}
