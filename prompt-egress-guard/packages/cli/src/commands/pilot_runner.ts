import fs from "node:fs";
import path from "node:path";
import {
  createAuditEvent,
  loadPolicyFile,
  scanPrompt,
  summarizeAuditEvents,
  type Action,
  type AuditEvent,
  type Policy,
  type ScanResult
} from "@prompt-egress-guard/core";
import { compileExtensionCommand } from "./compile_extension.js";
import { assessPilot } from "./pilot_assessment.js";
import { readPromptCorpus, validatePromptCorpus, writePilotInput } from "./pilot_input.js";
import { assessmentMarkdown, businessImpactReport, writeDecisionPacket } from "./pilot_report.js";
import type { PromptRecord } from "./pilot_schema.js";

export async function initPilotCommand(args: Record<string, string | boolean>): Promise<number> {
  const outputDir = String(args.output ?? args["output-dir"] ?? "");
  const pack = String(args.pack ?? "developer-workstation");
  if (!outputDir) {
    console.error("missing --output");
    return 1;
  }
  const inputDir = path.join(outputDir, "input");
  writePilotInput(inputDir, pack);
  console.log(`wrote ${outputDir}`);
  return 0;
}

export async function generateCorpusCommand(args: Record<string, string | boolean>): Promise<number> {
  const outputDir = String(args["output-dir"] ?? "");
  const pack = String(args.pack ?? "developer-workstation");
  if (!outputDir) {
    console.error("missing --output-dir");
    return 1;
  }
  writePilotInput(outputDir, pack);
  console.log(`wrote ${outputDir}`);
  return 0;
}

export async function validateCorpusCommand(args: Record<string, string | boolean>): Promise<number> {
  const inputDir = String(args.input ?? args["input-dir"] ?? "");
  const policyPath = typeof args.policy === "string" ? args.policy : undefined;
  if (!inputDir) {
    console.error("missing --input");
    return 1;
  }
  let policy: Policy | undefined;
  if (policyPath) {
    const result = loadPolicyFile(policyPath);
    if (!result.valid || !result.policy) {
      console.error(result.blockers.join("\n"));
      return 1;
    }
    policy = result.policy;
  }
  const validation = validatePromptCorpus(inputDir, policy);
  console.log(JSON.stringify(validation, null, 2));
  return validation.valid ? 0 : 1;
}

export async function pilotRunCommand(args: Record<string, string | boolean>): Promise<number> {
  const inputDir = String(args.input ?? args["input-dir"] ?? "");
  const outputDir = String(args.output ?? args["output-dir"] ?? "");
  const policyPath = String(args.policy ?? "examples/policies/default-policy.yml");
  if (!inputDir || !outputDir) {
    console.error("missing --input and/or --output");
    return 1;
  }
  const policyResult = loadPolicyFile(policyPath);
  if (!policyResult.valid || !policyResult.policy) {
    console.error(policyResult.blockers.join("\n"));
    return 1;
  }
  const corpusValidation = validatePromptCorpus(inputDir, policyResult.policy);
  if (!corpusValidation.valid) {
    console.error(corpusValidation.blockers.join("\n"));
    return 1;
  }
  fs.mkdirSync(path.join(outputDir, "scan-results"), { recursive: true });
  const records = readPromptCorpus(path.join(inputDir, "prompt_corpus.jsonl"));
  const auditEvents: AuditEvent[] = [];
  const scanResults: ScanResult[] = [];
  for (const record of records) {
    const result = scanRecord(policyResult.policy, record);
    scanResults.push(result);
    fs.writeFileSync(path.join(outputDir, "scan-results", `${record.prompt_id}.json`), `${JSON.stringify(result, null, 2)}\n`);
    if (result.action !== "ALLOW") auditEvents.push(createAuditEvent(policyResult.policy, result, userDecisionFor(result.action)));
  }
  fs.writeFileSync(path.join(outputDir, "scan_results.json"), `${JSON.stringify(scanResults, null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "local_audit.jsonl"), auditEvents.map((event) => JSON.stringify(event)).join("\n") + "\n");
  fs.writeFileSync(path.join(outputDir, "audit_summary.json"), `${JSON.stringify(summarizeAuditEvents(auditEvents, true), null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "business_impact_report.json"), `${JSON.stringify(businessImpactReport(scanResults), null, 2)}\n`);
  await compileExtensionCommand({ policy: policyPath, "output-dir": path.join(outputDir, "extension") });
  const assessment = assessPilot(inputDir, outputDir, policyResult.policy);
  fs.writeFileSync(path.join(outputDir, "pilot_assessment.json"), `${JSON.stringify(assessment, null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "pilot_summary.md"), assessmentMarkdown(assessment));
  fs.writeFileSync(path.join(outputDir, "real_world_assessment.json"), `${JSON.stringify(assessment, null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "real_world_assessment.md"), assessmentMarkdown(assessment));
  writeDecisionPacket(path.join(path.dirname(outputDir), "decision_packet"), assessment, outputDir, inputDir);
  console.log(`wrote ${outputDir}`);
  return 0;
}

export async function pilotReportCommand(args: Record<string, string | boolean>): Promise<number> {
  const inputDir = String(args.input ?? args["input-dir"] ?? "");
  const runDir = String(args.run ?? args["run-dir"] ?? "");
  const outputDir = String(args.output ?? args["output-dir"] ?? "");
  const policyPath = String(args.policy ?? "examples/policies/default-policy.yml");
  if (!inputDir || !runDir || !outputDir) {
    console.error("missing --input, --run, or --output");
    return 1;
  }
  const policyResult = loadPolicyFile(policyPath);
  if (!policyResult.valid || !policyResult.policy) {
    console.error(policyResult.blockers.join("\n"));
    return 1;
  }
  const assessment = assessPilot(inputDir, runDir, policyResult.policy);
  writeDecisionPacket(outputDir, assessment, runDir, inputDir);
  console.log(`wrote ${outputDir}`);
  return 0;
}

export async function pilotAssessCommand(args: Record<string, string | boolean>): Promise<number> {
  const inputDir = String(args.input ?? args["input-dir"] ?? "");
  const runDir = String(args.run ?? args["run-dir"] ?? "");
  const output = String(args.output ?? "");
  const policyPath = String(args.policy ?? "examples/policies/default-policy.yml");
  if (!inputDir || !runDir || !output) {
    console.error("missing --input, --run, or --output");
    return 1;
  }
  const policyResult = loadPolicyFile(policyPath);
  if (!policyResult.valid || !policyResult.policy) {
    console.error(policyResult.blockers.join("\n"));
    return 1;
  }
  const assessment = assessPilot(inputDir, runDir, policyResult.policy);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, `${JSON.stringify(assessment, null, 2)}\n`);
  console.log(`wrote ${output}`);
  return 0;
}

function scanRecord(policy: Policy, record: PromptRecord): ScanResult {
  if (record.element_type.endsWith("_negative") || record.element_type === "none_negative") {
    return {
      policy_id: policy.policy_id,
      site_id: record.site_id,
      action: "ALLOW",
      risk_status: "ALLOW",
      detected_risk_level: "NONE",
      base_action_from_score: "ALLOW",
      strongest_category_action: "ALLOW",
      final_action: "ALLOW",
      policy_mode: policy.mode,
      allowed_user_actions: ["submit"],
      decision_summary: "No configured prompt input was captured for this synthetic DOM scenario.",
      risk_score: 0,
      confidence: "LOW",
      categories: [],
      reason_codes: ["PROMPT_INPUT_NOT_FOUND", "ACTION_ALLOW"],
      redacted_excerpt: "",
      prompt_hash: "",
      warnings: ["PROMPT_INPUT_NOT_FOUND"],
      blockers: []
    };
  }
  return scanPrompt(policy, record.prompt, { site_id: record.site_id });
}

function userDecisionFor(action: Action): string {
  if (action === "REDIRECT") return "redirect_opened";
  if (action === "WARN") return "warn_ack_required";
  if (action === "BLOCK") return "blocked";
  return "allowed";
}
