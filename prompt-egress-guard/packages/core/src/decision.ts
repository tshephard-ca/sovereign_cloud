import { runDetectors } from "./detectors/index.js";
import type { Action, DetectorMatch, Policy, ScanResult } from "./models.js";
import { promptHash, redactText } from "./redaction.js";
import { actionFromThresholds, actionReason, aggregateConfidence, applyPolicyMode, categoryAction, combineScores, strongestAction } from "./scoring.js";

export interface ScanOptions {
  site_id?: string;
}

export function scanPrompt(policy: Policy, prompt: string, options: ScanOptions = {}): ScanResult {
  const siteId = options.site_id ?? policy.monitored_sites[0]?.site_id ?? "unknown_site";
  const warnings: string[] = [];
  const blockers: string[] = [];
  const reasonCodes: string[] = [];
  if (!prompt.trim()) {
    return {
      policy_id: policy.policy_id,
      site_id: siteId,
      action: "ALLOW",
      risk_status: "ALLOW",
      detected_risk_level: "NONE",
      base_action_from_score: "ALLOW",
      strongest_category_action: "ALLOW",
      final_action: "ALLOW",
      policy_mode: policy.mode,
      allowed_user_actions: ["submit"],
      decision_summary: "No prompt text was available to scan.",
      risk_score: 0,
      confidence: "LOW",
      categories: [],
      reason_codes: ["PROMPT_EMPTY", "ACTION_ALLOW"],
      redacted_excerpt: "",
      prompt_hash: "",
      warnings,
      blockers
    };
  }

  let scanText = prompt;
  if (prompt.length > policy.scanner.max_prompt_chars) {
    const half = Math.floor(policy.scanner.max_prompt_chars / 2);
    scanText = `${prompt.slice(0, half)}\n...\n${prompt.slice(-half)}`;
    warnings.push("PROMPT_TRUNCATED_FOR_SCAN");
    reasonCodes.push("PROMPT_TRUNCATED_FOR_SCAN");
  }

  const categoryResults = runDetectors(scanText, policy.scanner);
  const riskScore = combineScores(categoryResults);
  const confidence = aggregateConfidence(categoryResults);
  const baseAction = actionFromThresholds(riskScore, policy);
  const strongestCategoryAction = strongestAction(categoryResults.map((result) => categoryAction(result.category, policy)));
  const action = applyPolicyMode(strongestAction([baseAction, strongestCategoryAction]), policy);
  const allMatches: DetectorMatch[] = categoryResults.flatMap((result) => result.matches);
  const detectorCodes = categoryResults.flatMap((result) => result.reason_codes);
  const categories = [...new Set(categoryResults.map((result) => result.category))];
  reasonCodes.push("PROMPT_SCANNED", policyModeReason(policy.mode), ...detectorCodes, actionReason(action));
  if (action === "REDIRECT") reasonCodes.push("APPROVED_ENDPOINT_REDIRECT_RECOMMENDED");
  if (confidence === "LOW" && detectorCodes.length) warnings.push("LOW_CONFIDENCE_MATCH", "HIGH_FALSE_POSITIVE_RISK");
  return {
    policy_id: policy.policy_id,
    site_id: siteId,
    action,
    risk_status: action,
    detected_risk_level: detectedRiskLevel(riskScore, confidence),
    base_action_from_score: baseAction,
    strongest_category_action: strongestCategoryAction,
    final_action: action,
    policy_mode: policy.mode,
    allowed_user_actions: allowedUserActions(action, policy),
    decision_summary: decisionSummary(action, categories, confidence),
    risk_score: riskScore,
    confidence,
    categories,
    reason_codes: [...new Set(reasonCodes)],
    redacted_excerpt: redactText(scanText, policy.audit.max_redacted_excerpt_chars, allMatches),
    prompt_hash: policy.audit.store_prompt_hash ? promptHash(prompt) : "",
    warnings: [...new Set(warnings)],
    blockers
  };
}

function policyModeReason(mode: Policy["mode"]): string {
  if (mode === "observe") return "POLICY_MODE_OBSERVE";
  if (mode === "warn") return "POLICY_MODE_WARN";
  return "POLICY_MODE_ENFORCE";
}

function detectedRiskLevel(score: number, confidence: ScanResult["confidence"]): ScanResult["detected_risk_level"] {
  if (score === 0) return "NONE";
  if (confidence === "HIGH" || score >= 70) return "HIGH";
  if (confidence === "MEDIUM" || score >= 30) return "MEDIUM";
  return "LOW";
}

function allowedUserActions(action: Action, policy: Policy): string[] {
  if (action === "ALLOW") return ["submit"];
  if (action === "WARN" && policy.user_experience.allow_continue_on_warn) return ["cancel", "continue"];
  if (action === "REDIRECT") return policy.user_experience.allow_continue_on_redirect ? ["cancel", "open_approved_destination", "continue"] : ["cancel", "open_approved_destination"];
  if (action === "BLOCK" && policy.user_experience.allow_continue_on_block) return ["cancel", "continue"];
  return ["cancel"];
}

function decisionSummary(action: Action, categories: string[], confidence: ScanResult["confidence"]): string {
  const categoryText = categories.length ? categories.join(", ") : "no configured detector category";
  if (action === "ALLOW") return `No configured rule triggered above policy thresholds; confidence ${confidence}.`;
  if (action === "WARN") return `Warn before public-AI submission because ${categoryText} matched; confidence ${confidence}.`;
  if (action === "REDIRECT") return `Stop public-AI submission and offer approved-endpoint handoff because ${categoryText} matched; confidence ${confidence}.`;
  return `Block configured public-AI submission because ${categoryText} matched; confidence ${confidence}.`;
}
