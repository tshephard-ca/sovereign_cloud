import fs from "node:fs";
import path from "node:path";
import type { Action, ScanResult } from "@prompt-egress-guard/core";
import type { BusinessImpactFinding, GapFinding, PilotAssessment } from "./pilot_schema.js";

const businessFamilies: Array<{
  key: string;
  action?: Action;
  match: (code: string) => boolean;
  impact: string;
  question: string;
}> = [
  { key: "secrets_blocked", action: "BLOCK", match: (code) => /SECRET|TOKEN|PRIVATE_KEY|API_KEY/.test(code), impact: "Credential-like prompt submissions were stopped before public-AI egress.", question: "Which secure internal workflow should users follow after a credential-like prompt is blocked?" },
  { key: "source_code_redirected", action: "REDIRECT", match: (code) => /SOURCE_CODE|CODE_BLOCK|REPOSITORY|STACK_TRACE/.test(code), impact: "Source-code-like work was steered toward an approved endpoint instead of a public-AI submission.", question: "Should developer workflows default to redirect rather than warn?" },
  { key: "customer_records_redirected", action: "REDIRECT", match: (code) => /CUSTOMER|ACCOUNT|SUPPORT/.test(code), impact: "Customer-record-like prompts were redirected for approved handling.", question: "Which customer identifiers should trigger redirect versus warn?" },
  { key: "health_data_blocked", action: "BLOCK", match: (code) => /HEALTH|PATIENT|CLINICAL|MEDICATION/.test(code), impact: "Health-data-like prompts were blocked under the configured policy.", question: "Should health-data-like prompts always block, or are approved redirects allowed for some teams?" },
  { key: "legal_text_redirected", action: "REDIRECT", match: (code) => /LEGAL|CONTRACT|LITIGATION|MATTER/.test(code), impact: "Legal-sensitive text candidates were redirected to approved handling.", question: "Should legal-sensitive text be redirected, blocked, or reviewed by a policy owner?" },
  { key: "financial_data_blocked", action: "BLOCK", match: (code) => /PAYMENT|BANK|PAYROLL|TAX/.test(code), impact: "Financial-sensitive prompts were blocked before public-AI submission.", question: "Which finance workflows need a sanctioned alternative path?" },
  { key: "personal_data_warned", action: "WARN", match: (code) => /EMAIL|PHONE|ADDRESS|DOB/.test(code), impact: "Personal-data-like prompts required review before continuing.", question: "Should personal-data-like prompts remain warn-only or move to redirect for some teams?" },
  { key: "internal_identifiers_warned", action: "WARN", match: (code) => /INTERNAL|PRIVATE_IP/.test(code), impact: "Internal identifiers triggered user review before public-AI submission.", question: "Which internal identifiers are acceptable in public prompts, if any?" }
];

export function businessImpactReport(results: ScanResult[]): BusinessImpactFinding[] {
  const output = new Map<string, BusinessImpactFinding>();
  for (const result of results) {
    for (const family of businessFamilies) {
      if (family.action && family.action !== result.action) continue;
      if (!result.reason_codes.some(family.match)) continue;
      output.set(`${result.action}:${family.key}`, {
        code: family.key.toUpperCase(),
        action: result.action,
        impact: family.impact,
        question: family.question
      });
    }
  }
  return [...output.values()].sort((a, b) => `${a.action}:${a.code}`.localeCompare(`${b.action}:${b.code}`));
}

export function adminQuestions(findings: BusinessImpactFinding[], gaps: GapFinding[]): string[] {
  return [
    ...findings.map((finding) => finding.question),
    ...gaps.map((gap) => gap.suggested_fix)
  ].filter((question, index, all) => all.indexOf(question) === index);
}

export function assessmentMarkdown(assessment: PilotAssessment): string {
  const lines = [
    "# Prompt Egress Pilot Summary",
    "",
    `Status: **${assessment.status}**`,
    "",
    assessment.executive_summary.core_message,
    "",
    "## Business Impact",
    "",
    `- Protected workflows exercised: ${assessment.executive_summary.protected_workflow_count}`,
    `- Configured public-AI sites exercised: ${assessment.executive_summary.configured_site_count}`,
    `- Risky prompt candidates: ${assessment.executive_summary.risky_prompt_count}`,
    `- Blocked: ${assessment.executive_summary.blocked_count}`,
    `- Redirected: ${assessment.executive_summary.redirected_count}`,
    `- Warned: ${assessment.executive_summary.warned_count}`,
    `- Allowed controls: ${assessment.executive_summary.allowed_count}`,
    "",
    "## Workflow Evidence",
    "",
    "| Workflow | Expected | Actual | Categories | Business meaning |",
    "| --- | --- | --- | --- | --- |"
  ];
  for (const row of assessment.workflow_table) {
    lines.push(`| ${row.workflow} | \`${row.expected_action}\` | \`${row.actual_action ?? "MISSING"}\` | ${row.categories.join(", ") || "none"} | ${row.business_meaning} |`);
  }
  lines.push("", "## Pilot Coverage", "");
  lines.push(`- Detector categories covered: ${String(assessment.input_coverage.category_count)}.`);
  lines.push(`- Action paths covered: ${(assessment.input_coverage.actions as string[] | undefined)?.join(", ") ?? "unknown"}.`);
  lines.push(`- DOM input types covered: ${(assessment.input_coverage.element_types as string[] | undefined)?.join(", ") ?? "unknown"}.`);
  lines.push(`- Submit paths covered: ${(assessment.input_coverage.submit_paths as string[] | undefined)?.join(", ") ?? "unknown"}.`);
  lines.push("", "## Business Findings", "");
  for (const finding of assessment.business_impact_findings) lines.push(`- **${finding.action}** ${finding.code}: ${finding.impact}`);
  if (assessment.business_impact_findings.length === 0) lines.push("- None.");
  lines.push("", "## Gaps", "", "### Input Gaps", "");
  lines.push(...gapLines(assessment.input_gaps));
  lines.push("", "### Output Gaps", "");
  lines.push(...gapLines(assessment.output_gaps));
  lines.push("", "## Admin Questions", "");
  for (const question of assessment.admin_questions) lines.push(`- ${question}`);
  if (assessment.admin_questions.length === 0) lines.push("- None.");
  lines.push("", "## Caveats", "");
  lines.push("- This is a synthetic pilot evidence pack, not compliance proof.");
  lines.push("- DOM-level inspection covers configured web pages only.");
  lines.push("- Pattern matching can false-positive and false-negative.");
  lines.push("- Public-AI site DOM changes can make selectors stale.");
  lines.push("- Native apps, mobile apps, API clients, unmanaged browsers, and unconfigured sites are out of scope.");
  return `${lines.join("\n")}\n`;
}

export function writeDecisionPacket(outputDir: string, assessment: PilotAssessment, runDir: string, inputDir: string): void {
  fs.mkdirSync(outputDir, { recursive: true });
  fs.writeFileSync(path.join(outputDir, "pilot_summary.md"), assessmentMarkdown(assessment));
  fs.writeFileSync(path.join(outputDir, "pilot_assessment.json"), `${JSON.stringify(assessment, null, 2)}\n`);
  const manifest = {
    packet_version: 1,
    review_only: true,
    generated_at: "2026-01-01T00:00:00Z",
    input_hash: directoryHash(inputDir),
    run_hash: directoryHash(runDir),
    artifacts: ["pilot_summary.md", "pilot_assessment.json", "manifest.json"]
  };
  fs.writeFileSync(path.join(outputDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
}

function gapLines(gaps: GapFinding[]): string[] {
  if (gaps.length === 0) return ["- None."];
  return gaps.map((gap) => `- ${gap.code}: ${gap.description} Business impact: ${gap.business_impact} Suggested fix: ${gap.suggested_fix}`);
}

function directoryHash(dir: string): string {
  const files = walk(dir).filter((file) => fs.statSync(file).isFile()).sort();
  let hash = 0;
  for (const file of files) {
    const rel = path.relative(dir, file);
    const text = `${rel}\n${fs.readFileSync(file, "utf8")}`;
    for (let index = 0; index < text.length; index += 1) hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

function walk(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    return fs.statSync(full).isDirectory() ? walk(full) : [full];
  });
}
