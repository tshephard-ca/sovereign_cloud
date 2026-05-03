import fs from "node:fs";
import path from "node:path";
import type { Policy } from "@prompt-egress-guard/core";
import type { PromptRecord } from "./pilot_schema.js";

export const PILOT_PACKS = ["developer-workstation", "support-team", "health-data-strict", "legal-review", "finance-strict", "public-sector", "education", "warn-only-pilot", "strict-enforcement"] as const;
export type PilotPack = (typeof PILOT_PACKS)[number];

export function writePilotInput(outputDir: string, pack: string = "developer-workstation"): void {
  const records = pilotRecords(pack);
  fs.mkdirSync(path.join(outputDir, "prompts"), { recursive: true });
  for (const record of records) fs.writeFileSync(path.join(outputDir, "prompts", `${record.prompt_id}.txt`), record.prompt);
  fs.writeFileSync(path.join(outputDir, "prompt_corpus.jsonl"), records.map((record) => JSON.stringify(record)).join("\n") + "\n");
  fs.writeFileSync(path.join(outputDir, "dom_scenarios.json"), `${JSON.stringify(domScenarios(records), null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "policy_modes.json"), `${JSON.stringify(["observe", "warn", "enforce"], null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "unsafe_policy_cases.json"), `${JSON.stringify(unsafePolicyCases(), null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "business_context.json"), `${JSON.stringify(businessContext(records, pack), null, 2)}\n`);
}

export function readPromptCorpus(file: string): PromptRecord[] {
  return fs
    .readFileSync(file, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line) as PromptRecord);
}

export function validatePromptCorpus(inputDir: string, policy?: Policy): { valid: boolean; warnings: string[]; blockers: string[] } {
  const warnings: string[] = [];
  const blockers: string[] = [];
  const corpusPath = path.join(inputDir, "prompt_corpus.jsonl");
  if (!fs.existsSync(corpusPath)) return { valid: false, warnings, blockers: ["PROMPT_CORPUS_MISSING"] };
  const records = readPromptCorpus(corpusPath);
  if (records.length < 8) warnings.push("PILOT_CORPUS_SMALL");
  const ids = new Set<string>();
  for (const record of records) {
    if (ids.has(record.prompt_id)) blockers.push(`DUPLICATE_PROMPT_ID: ${record.prompt_id}`);
    ids.add(record.prompt_id);
    if (!record.synthetic) warnings.push(`NON_SYNTHETIC_PROMPT_REQUIRES_REVIEW: ${record.prompt_id}`);
    if (!record.prompt && record.element_type !== "none_negative") blockers.push(`PROMPT_TEXT_MISSING: ${record.prompt_id}`);
  }
  if (policy) {
    const sites = new Set(policy.monitored_sites.map((site) => site.site_id));
    for (const record of records) {
      if (!sites.has(record.site_id)) blockers.push(`PROMPT_SITE_NOT_IN_POLICY: ${record.prompt_id}`);
    }
  }
  return { valid: blockers.length === 0, warnings: [...new Set(warnings)], blockers: [...new Set(blockers)] };
}

export function pilotRecords(pack: string = "developer-workstation"): PromptRecord[] {
  const fixture = readPackFixture(pack);
  if (fixture.length) return fixture.map(normalizeGeneratedBodies);
  const records = baseRecords();
  if (pack === "support-team") return focusRecords(records, ["safe_public_summary", "customer_support_record", "personal_contact_warn", "prompt_not_found_negative"]);
  if (pack === "health-data-strict") return focusRecords(records, ["safe_public_summary", "health_case_note", "personal_contact_warn", "prompt_not_found_negative"], { personal_contact_warn: "BLOCK" });
  if (pack === "legal-review") return focusRecords(records, ["safe_public_summary", "legal_sensitive_text", "customer_support_record", "prompt_not_found_negative"]);
  if (pack === "finance-strict") return focusRecords(records, ["safe_public_summary", "financial_card_payroll", "secret_bearer_token", "prompt_not_found_negative"]);
  if (pack === "public-sector") return focusRecords(records, ["safe_public_summary", "internal_identifier_warn", "personal_contact_warn", "prompt_not_found_negative"], { internal_identifier_warn: "REDIRECT", personal_contact_warn: "REDIRECT" });
  if (pack === "education") return focusRecords(records, ["safe_public_summary", "personal_contact_warn", "customer_support_record", "prompt_not_found_negative"], { customer_support_record: "WARN" });
  if (pack === "warn-only-pilot") {
    return focusRecords(records, ["safe_public_summary", "developer_source_code", "secret_bearer_token", "customer_support_record", "personal_contact_warn", "prompt_not_found_negative"], {
      developer_source_code: "WARN",
      secret_bearer_token: "WARN",
      customer_support_record: "WARN"
    });
  }
  if (pack === "strict-enforcement") return focusRecords(records, ["safe_public_summary", "secret_bearer_token", "health_case_note", "financial_card_payroll", "developer_source_code", "prompt_not_found_negative"], { developer_source_code: "BLOCK" });
  return records;
}

function focusRecords(records: PromptRecord[], ids: string[], expectedActionOverrides: Partial<Record<string, PromptRecord["expected_action"]>> = {}): PromptRecord[] {
  const selected = records.filter((record) => ids.includes(record.prompt_id));
  return selected.map((record) => ({ ...record, site_id: "public_ai_1", expected_action: expectedActionOverrides[record.prompt_id] ?? record.expected_action }));
}

function readPackFixture(pack: string): PromptRecord[] {
  const file = path.join("examples", "pilot-packs", pack, "prompt_corpus.jsonl");
  if (!fs.existsSync(file)) return [];
  return readPromptCorpus(file);
}

function baseRecords(): PromptRecord[] {
  return [
    record("safe_public_summary", "public_ai_1", "textarea", "button_click", "public research summary", "ALLOW", [], "none", "Summarize this public product announcement in three bullets.", "Negative control for allow path."),
    record("developer_source_code", "public_ai_1", "textarea", "ctrl_enter", "developer code review", "REDIRECT", ["source_code", "internal_identifiers"], "source_code", "Review this source-code-like content.\n```ts\nimport { runJob } from './internal/queue';\nexport function processOrder(orderId: string) {\n  // TODO BUG-1234 retry path\n  return runJob({ orderId, env: 'prod' });\n}\n```", "Redirects developer workflow to approved endpoint."),
    record("secret_bearer_token", "public_ai_2", "input_text", "form_submit", "configuration troubleshooting", "BLOCK", ["secrets"], "secrets", "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789 should not be sent.", "Secret-like value block path."),
    record("health_case_note", "public_ai_2", "role_textbox", "cmd_enter", "health-data-like note rewrite", "BLOCK", ["health_data"], "health_data", "patient_id: PT-2048 diagnosis: elevated glucose medication: test medicine 10 mg symptoms: dizziness", "Health-data-like block path."),
    record("customer_support_record", "public_ai_3", "textarea", "button_click", "support response drafting", "REDIRECT", ["customer_records", "personal_data"], "customer_records", "Draft a reply for customer_id: CUST-102030 support ticket TCK-100200 Name: Taylor Example Email: taylor.example@example.invalid Account status: renewal pending.", "Customer-record-like redirect path."),
    record("legal_sensitive_text", "public_ai_4", "contenteditable", "button_click", "legal text drafting", "REDIRECT", ["legal_text"], "legal_text", "Privileged and confidential legal-sensitive text candidate. Matter number MAT-2026-1045. Draft settlement agreement and litigation strategy section.", "Legal-sensitive redirect path."),
    record("financial_card_payroll", "public_ai_5", "textarea", "form_submit", "finance operations", "BLOCK", ["financial_data"], "financial_data", "Payroll review with payment card candidate 4111 1111 1111 1111 and bank_account: 100200300.", "Financial-sensitive block path."),
    record("personal_contact_warn", "public_ai_5", "textarea", "plain_enter_disabled", "contact cleanup", "WARN", ["personal_data"], "personal_data", "Please normalize this contact: Taylor Example, taylor.example@example.invalid, +1 555 010 2222.", "Warning path with explicit continue requirement."),
    record("internal_identifier_warn", "public_ai_1", "textarea", "button_click", "operations note", "WARN", ["internal_identifiers"], "internal_identifiers", "Check whether prod db01.internal at 10.0.0.4 relates to INC-1001.", "Internal identifier warn path."),
    record("long_prompt_truncated", "public_ai_2", "textarea", "button_click", "large paste with trailing secret", "BLOCK", ["secrets"], "secrets", generatedLongPrompt(), "Exercises max prompt truncation while scanning first and last chunks."),
    record("password_field_negative", "public_ai_3", "password_negative", "no_submit", "non-captured credential field", "ALLOW", [], "none", "password=ShouldNotBeCaptured1234567890", "DOM capture negative: password fields must be ignored."),
    record("file_field_negative", "public_ai_4", "file_negative", "no_submit", "non-captured file input", "ALLOW", [], "none", "file-content-placeholder", "DOM capture negative: file contents must not be read."),
    record("prompt_not_found_negative", "public_ai_5", "none_negative", "no_submit", "stale selector simulation", "ALLOW", [], "none", "", "No prompt found should warn and allow by default.")
  ];
}

function normalizeGeneratedBodies(record: PromptRecord): PromptRecord {
  if (record.prompt_id !== "long_prompt_truncated") return record;
  if (record.prompt.length > 20000) return record;
  return { ...record, prompt: generatedLongPrompt() };
}

function generatedLongPrompt(): string {
  return `${"public context ".repeat(1800)}\napi_key=ABCDEFGHIJKLMNOPQRSTUVWX1234567890`;
}

function record(
  prompt_id: string,
  site_id: string,
  element_type: PromptRecord["element_type"],
  submit_path: PromptRecord["submit_path"],
  business_workflow: string,
  expected_action: PromptRecord["expected_action"],
  expected_categories: PromptRecord["expected_categories"],
  sensitivity_family: PromptRecord["sensitivity_family"],
  prompt: string,
  notes: string
): PromptRecord {
  return { prompt_id, site_id, element_type, submit_path, business_workflow, expected_action, expected_categories, sensitivity_family, synthetic: true, prompt, notes };
}

function domScenarios(records: PromptRecord[]): unknown[] {
  return records.map((record) => ({
    prompt_id: record.prompt_id,
    site_id: record.site_id,
    element_type: record.element_type,
    submit_path: record.submit_path,
    should_capture: !record.element_type.endsWith("_negative") && record.element_type !== "none_negative"
  }));
}

function unsafePolicyCases(): unknown[] {
  return [
    { case_id: "include_prompt_without_ack", expected_blocker: "UNSAFE_PROMPT_TRANSFER_WITHOUT_ACK" },
    { case_id: "raw_prompt_storage_without_ack", expected_blocker: "RAW_PROMPT_STORAGE_WITHOUT_ACK" },
    { case_id: "broad_host_permission_without_ack", expected_blocker: "UNSAFE_BROAD_HOST_PERMISSIONS_WITHOUT_ACK" }
  ];
}

function businessContext(records: PromptRecord[], pack: string): unknown {
  return {
    generated_at: "2026-01-01T00:00:00Z",
    pilot_pack: pack,
    synthetic_prompts: true,
    workflow_count: new Set(records.map((record) => record.business_workflow)).size,
    workflows: records.map((record) => ({ prompt_id: record.prompt_id, workflow: record.business_workflow, expected_action: record.expected_action }))
  };
}
