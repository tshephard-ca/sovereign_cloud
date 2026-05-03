import fs from "node:fs";
import path from "node:path";
import type { Action, Policy, ScanResult } from "@prompt-egress-guard/core";
import { adminQuestions, businessImpactReport } from "./pilot_report.js";
import { readPromptCorpus } from "./pilot_input.js";
import type { GapFinding, PilotAssessment, PromptRecord } from "./pilot_schema.js";

export function assessPilot(inputDir: string, runDir: string, policy: Policy): PilotAssessment {
  const records = readPromptCorpus(path.join(inputDir, "prompt_corpus.jsonl"));
  const scanResults = readJsonIfExists<ScanResult[]>(path.join(runDir, "scan_results.json"), []);
  const auditSummary = readJsonIfExists<Record<string, unknown>>(path.join(runDir, "audit_summary.json"), {});
  const extensionManifest = readJsonIfExists<Record<string, unknown>>(path.join(runDir, "extension", "manifest.json"), {});
  const dnrRules = readJsonIfExists<unknown[]>(path.join(runDir, "extension", "dnr_rules.json"), []);
  const inputCoverage = inputCoverageFor(records, inputDir, policy);
  const outputCoverage = outputCoverageFor(records, scanResults, auditSummary, extensionManifest, dnrRules, runDir, policy);
  const inputGaps = inputGapsFor(inputCoverage);
  const outputGaps = outputGapsFor(outputCoverage, policy);
  const impact = businessImpactReport(scanResults);
  const workflowTable = workflowTableFor(records, scanResults);
  const questions = adminQuestions(impact, [...inputGaps, ...outputGaps]);
  return {
    status: inputGaps.length === 0 && outputGaps.length === 0 ? "PASS" : "REVIEW",
    executive_summary: executiveSummary(records, scanResults, policy),
    input_coverage: inputCoverage,
    output_coverage: outputCoverage,
    workflow_table: workflowTable,
    business_impact_findings: impact,
    admin_questions: questions,
    input_gaps: inputGaps,
    output_gaps: outputGaps
  };
}

function executiveSummary(records: PromptRecord[], results: ScanResult[], policy: Policy): PilotAssessment["executive_summary"] {
  const counts = countActions(results);
  const risky = results.filter((result) => result.action !== "ALLOW").length;
  return {
    protected_workflow_count: new Set(records.map((record) => record.business_workflow)).size,
    configured_site_count: policy.monitored_sites.length,
    risky_prompt_count: risky,
    blocked_count: counts.BLOCK ?? 0,
    redirected_count: counts.REDIRECT ?? 0,
    warned_count: counts.WARN ?? 0,
    allowed_count: counts.ALLOW ?? 0,
    core_message: `Synthetic pilot evidence shows ${risky} risky prompt candidates were stopped, redirected, or warned before configured public-AI submission while safe controls remained allowed.`
  };
}

function workflowTableFor(records: PromptRecord[], results: ScanResult[]): PilotAssessment["workflow_table"] {
  return records.map((record, index) => {
    const result = results[index];
    return {
      prompt_id: record.prompt_id,
      workflow: record.business_workflow,
      expected_action: record.expected_action,
      actual_action: result?.action,
      categories: record.expected_categories,
      business_meaning: meaningFor(result?.action ?? record.expected_action, record.sensitivity_family)
    };
  });
}

function inputCoverageFor(records: PromptRecord[], inputDir: string, policy: Policy): Record<string, unknown> {
  const expectedCategories = new Set(records.flatMap((record) => record.expected_categories));
  const actions = new Set(records.map((record) => record.expected_action));
  const sites = new Set(records.map((record) => record.site_id));
  const elementTypes = new Set(records.map((record) => record.element_type));
  const submitPaths = new Set(records.map((record) => record.submit_path));
  return {
    prompt_count: records.length,
    category_count: expectedCategories.size,
    categories: [...expectedCategories].sort(),
    action_count: actions.size,
    actions: [...actions].sort(),
    site_count: sites.size,
    monitored_policy_site_count: policy.monitored_sites.length,
    element_types: [...elementTypes].sort(),
    submit_paths: [...submitPaths].sort(),
    has_business_context: fs.existsSync(path.join(inputDir, "business_context.json")),
    has_dom_scenarios: fs.existsSync(path.join(inputDir, "dom_scenarios.json")),
    has_policy_mode_variants: fs.existsSync(path.join(inputDir, "policy_modes.json")),
    has_unsafe_policy_cases: fs.existsSync(path.join(inputDir, "unsafe_policy_cases.json")),
    has_truncation_case: records.some((record) => record.prompt.length > policy.scanner.max_prompt_chars),
    has_no_prompt_case: records.some((record) => record.element_type === "none_negative"),
    has_password_negative_case: records.some((record) => record.element_type === "password_negative"),
    has_file_negative_case: records.some((record) => record.element_type === "file_negative"),
    has_allow_negative_control: actions.has("ALLOW"),
    has_selector_staleness_case: records.some((record) => record.prompt_id === "prompt_not_found_negative")
  };
}

function outputCoverageFor(records: PromptRecord[], scanResults: ScanResult[], auditSummary: Record<string, unknown>, extensionManifest: Record<string, unknown>, dnrRules: unknown[], runDir: string, policy: Policy): Record<string, unknown> {
  const rawScan = fs.existsSync(path.join(runDir, "scan_results.json")) ? fs.readFileSync(path.join(runDir, "scan_results.json"), "utf8") : "";
  const actionSet = new Set(scanResults.map((result) => result.action));
  const reasonCodes = new Set(scanResults.flatMap((result) => result.reason_codes));
  const resultCountMatches = scanResults.length === records.length;
  const expectedActionMatches = scanResults.every((result, index) => result.action === records[index]?.expected_action);
  return {
    scan_result_count: scanResults.length,
    expected_scan_result_count: records.length,
    result_count_matches: resultCountMatches,
    expected_action_matches: expectedActionMatches,
    actions: [...actionSet].sort(),
    reason_code_count: reasonCodes.size,
    has_redirect_result: actionSet.has("REDIRECT"),
    has_block_result: actionSet.has("BLOCK"),
    has_warn_result: actionSet.has("WARN"),
    has_allow_result: actionSet.has("ALLOW"),
    has_clear_decision_fields: scanResults.every((result) => Boolean(result.final_action && result.detected_risk_level && result.decision_summary)),
    has_prompt_hashes: scanResults.every((result) => (result.action === "ALLOW" && result.prompt_hash === "" ? true : result.prompt_hash.length === 16)),
    has_redacted_excerpts: scanResults.some((result) => result.redacted_excerpt.includes("<")),
    raw_secret_absent_from_scan_output: !rawScan.includes("abcdefghijklmnopqrstuvwxyz0123456789") && !rawScan.includes("ABCDEFGHIJKLMNOPQRSTUVWX1234567890"),
    audit_event_count: auditSummary.event_count ?? 0,
    has_audit_summary: Boolean(auditSummary.event_count),
    impact_finding_count: businessImpactReport(scanResults).length,
    has_business_impact_report: fs.existsSync(path.join(runDir, "business_impact_report.json")),
    has_extension_manifest: Boolean(extensionManifest.manifest_version),
    manifest_host_permission_count: Array.isArray(extensionManifest.host_permissions) ? extensionManifest.host_permissions.length : 0,
    dnr_enabled: policy.dnr.enabled,
    has_dnr_rules: dnrRules.length > 0,
    dnr_rule_expectation_met: policy.dnr.enabled ? dnrRules.length >= policy.monitored_sites.length : dnrRules.length === 0,
    has_content_script_bundle: fs.existsSync(path.join(runDir, "extension", "content_script.js")),
    has_service_worker_bundle: fs.existsSync(path.join(runDir, "extension", "service_worker.js")),
    deterministic_ordering: scanResults.map((result) => result.site_id).join("|") === records.map((record) => record.site_id).join("|")
  };
}

function inputGapsFor(coverage: Record<string, unknown>): GapFinding[] {
  const gaps: GapFinding[] = [];
  check(gaps, "input", coverage.category_count === 8, "INPUT_CATEGORY_COVERAGE_INCOMPLETE", "Generated prompts do not cover every detector category.", "Detector blind spots may remain untested.", "Add prompts for every detector category.");
  check(gaps, "input", coverage.action_count === 4, "INPUT_ACTION_COVERAGE_INCOMPLETE", "Generated prompts do not cover ALLOW, WARN, REDIRECT, and BLOCK.", "Policy action paths may be under-tested.", "Add prompt records for all action outcomes.");
  check(gaps, "input", coverage.site_count === coverage.monitored_policy_site_count, "INPUT_SITE_COVERAGE_INCOMPLETE", "Generated prompts do not cover all configured public-AI site profiles.", "A site selector profile may not be exercised.", "Add records for every monitored site.");
  for (const key of ["has_business_context", "has_dom_scenarios", "has_policy_mode_variants", "has_unsafe_policy_cases", "has_truncation_case", "has_no_prompt_case", "has_password_negative_case", "has_file_negative_case", "has_allow_negative_control", "has_selector_staleness_case"]) {
    check(gaps, "input", Boolean(coverage[key]), `INPUT_${key.toUpperCase()}_MISSING`, `Generated input missing ${key}.`, "Generated evidence may not reflect field deployment edge cases.", `Add fixture support for ${key}.`);
  }
  return gaps;
}

function outputGapsFor(coverage: Record<string, unknown>, policy: Policy): GapFinding[] {
  const gaps: GapFinding[] = [];
  const checks: Array<[boolean, string, string, string, string]> = [
    [Boolean(coverage.result_count_matches), "OUTPUT_SCAN_RESULT_COVERAGE_INCOMPLETE", "Not every generated prompt has a scan result.", "Some generated behavior is not validated.", "Scan every generated prompt."],
    [Boolean(coverage.expected_action_matches), "OUTPUT_EXPECTED_ACTION_MISMATCH", "Scan results do not match generated expected actions.", "Business-impact conclusions may be misleading.", "Adjust detectors, scoring, or fixture expectations."],
    [Boolean(coverage.has_clear_decision_fields), "OUTPUT_DECISION_FIELDS_MISSING", "Scan results do not include clear final-action and risk-level fields.", "Reviewers cannot distinguish detection from policy action.", "Emit final_action, detected_risk_level, and decision_summary."],
    [Boolean(coverage.has_redirect_result), "OUTPUT_REDIRECT_EVIDENCE_MISSING", "No redirect result was produced.", "Approved endpoint handoff path is not validated.", "Add redirect-triggering prompts."],
    [Boolean(coverage.has_block_result), "OUTPUT_BLOCK_EVIDENCE_MISSING", "No block result was produced.", "High-risk stop path is not validated.", "Add block-triggering prompts."],
    [Boolean(coverage.has_warn_result), "OUTPUT_WARN_EVIDENCE_MISSING", "No warning result was produced.", "Warn-and-continue path is not validated.", "Add warn-triggering prompts."],
    [Boolean(coverage.has_allow_result), "OUTPUT_ALLOW_EVIDENCE_MISSING", "No allow result was produced.", "Negative control is missing.", "Add safe prompt cases."],
    [Boolean(coverage.has_prompt_hashes), "OUTPUT_PROMPT_HASH_EVIDENCE_MISSING", "Prompt hashes are missing from non-empty scan results.", "Audit correlation may be weaker.", "Enable prompt hash output."],
    [Boolean(coverage.has_redacted_excerpts), "OUTPUT_REDACTED_EXCERPTS_MISSING", "Redacted excerpts are not present.", "Users may not understand why a rule fired.", "Enable short redacted excerpts."],
    [Boolean(coverage.raw_secret_absent_from_scan_output), "OUTPUT_RAW_SECRET_LEAK", "Raw synthetic secrets appear in scan output.", "Audit/report outputs may expose sensitive content.", "Fix redaction before writing outputs."],
    [Boolean(coverage.has_audit_summary), "OUTPUT_AUDIT_SUMMARY_MISSING", "Audit summary was not generated.", "Review-only reporting path is missing.", "Export redacted audit summary."],
    [Boolean(coverage.has_extension_manifest), "OUTPUT_EXTENSION_MANIFEST_MISSING", "Compiled extension manifest is missing.", "Extension build path is not validated.", "Run compile-extension."],
    [Number(coverage.manifest_host_permission_count) >= policy.monitored_sites.length, "OUTPUT_HOST_PERMISSION_EVIDENCE_MISSING", "Manifest host permissions do not cover configured sites.", "Extension may not run on expected configured sites.", "Generate host permissions from policy."],
    [Boolean(coverage.dnr_rule_expectation_met), "OUTPUT_DNR_RULE_EXPECTATION_MISMATCH", "DNR rules do not match configured DNR mode.", "Domain-scope artifacts may confuse content-script pilot behavior.", "Keep DNR disabled for content-script pilots or explicitly generate DNR rules."],
    [Boolean(coverage.has_content_script_bundle), "OUTPUT_CONTENT_SCRIPT_BUNDLE_MISSING", "Content script bundle missing.", "DOM capture cannot be installed.", "Build extension content script."],
    [Boolean(coverage.has_service_worker_bundle), "OUTPUT_SERVICE_WORKER_BUNDLE_MISSING", "Service worker bundle missing.", "Extension background support path is missing.", "Build extension service worker."],
    [Boolean(coverage.deterministic_ordering), "OUTPUT_DETERMINISTIC_ORDERING_MISSING", "Output order does not match input order.", "Diff-based review is harder.", "Sort outputs deterministically."]
  ];
  for (const [ok, code, description, impact, fix] of checks) check(gaps, "output", ok, code, description, impact, fix);
  return gaps;
}

function check(gaps: GapFinding[], area: "input" | "output", ok: boolean, code: string, description: string, businessImpact: string, suggestedFix: string): void {
  if (!ok) gaps.push({ area, severity: "REVIEW", code, description, business_impact: businessImpact, suggested_fix: suggestedFix });
}

function countActions(results: ScanResult[]): Record<Action, number> {
  return results.reduce((counts, result) => {
    counts[result.action] = (counts[result.action] ?? 0) + 1;
    return counts;
  }, {} as Record<Action, number>);
}

function meaningFor(action: Action, family: string): string {
  if (action === "ALLOW") return "Safe or non-captured control path preserved.";
  if (action === "WARN") return `${family} prompt candidate requires user review before continuing.`;
  if (action === "REDIRECT") return `${family} prompt candidate is steered to approved endpoint handoff.`;
  return `${family} prompt candidate is blocked before configured public-AI submission.`;
}

function readJsonIfExists<T>(file: string, fallback: T): T {
  if (!fs.existsSync(file)) return fallback;
  return JSON.parse(fs.readFileSync(file, "utf8")) as T;
}
