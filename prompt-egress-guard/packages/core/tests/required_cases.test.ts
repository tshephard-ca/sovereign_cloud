import fs from "node:fs";
import yaml from "js-yaml";
import { describe, expect, it } from "vitest";
import { PolicySchema, scanPrompt, validateApprovedUrl, validatePolicy } from "@prompt-egress-guard/core";

const policy = PolicySchema.parse(yaml.load(fs.readFileSync("examples/policies/default-policy.yml", "utf8")));

describe("required policy and scan edge cases", () => {
  it.each([
    ["https://approved-ai.example.invalid/", true],
    ["http://localhost:8080/", true],
    ["http://approved-ai.example.test/", false]
  ])("validates approved destination URL safety for %s", (url, valid) => {
    expect(validateApprovedUrl(url).valid).toBe(valid);
  });

  it("returns PROMPT_EMPTY for empty prompt without scanning content", () => {
    const result = scanPrompt(policy, "   ");
    expect(result.action).toBe("ALLOW");
    expect(result.reason_codes).toContain("PROMPT_EMPTY");
  });

  it("adds truncation warning for long prompts", () => {
    const long = `${"A".repeat(policy.scanner.max_prompt_chars + 100)} api_key=abcdefghijklmnopqrstuvwx`;
    const result = scanPrompt(policy, long);
    expect(result.warnings).toContain("PROMPT_TRUNCATED_FOR_SCAN");
    expect(result.reason_codes).toContain("PROMPT_TRUNCATED_FOR_SCAN");
  });

  it("observe mode never enforces block or redirect", () => {
    const observe = structuredClone(policy);
    observe.mode = "observe";
    const result = scanPrompt(observe, "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789");
    expect(result.action).toBe("ALLOW");
    expect(result.reason_codes).toContain("POLICY_MODE_OBSERVE");
  });

  it("warn mode converts stronger actions to WARN", () => {
    const warnOnly = structuredClone(policy);
    warnOnly.mode = "warn";
    const result = scanPrompt(warnOnly, "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789");
    expect(result.action).toBe("WARN");
    expect(result.final_action).toBe("WARN");
    expect(result.base_action_from_score).toBe("BLOCK");
    expect(result.strongest_category_action).toBe("BLOCK");
    expect(result.detected_risk_level).toBe("HIGH");
    expect(result.allowed_user_actions).toEqual(["cancel", "continue"]);
    expect(result.decision_summary).toContain("Warn before public-AI submission");
    expect(result.reason_codes).toContain("POLICY_MODE_WARN");
  });

  it("category actions are all valid action values", () => {
    const parsed = validatePolicy(policy);
    expect(parsed.valid).toBe(true);
    expect(Object.values(policy.actions.category_actions).sort()).toEqual(["BLOCK", "BLOCK", "BLOCK", "REDIRECT", "REDIRECT", "REDIRECT", "WARN", "WARN"]);
  });

  it.each([
    ["examples/prompts/secrets_prompt.txt", "BLOCK", "BEARER_TOKEN_DETECTED"],
    ["examples/prompts/health_record_prompt.txt", "BLOCK", "HEALTH_RECORD_PATTERN_DETECTED"],
    ["examples/prompts/legal_text_prompt.txt", "REDIRECT", "LEGAL_PRIVILEGE_PATTERN_DETECTED"],
    ["examples/prompts/customer_record_prompt.txt", "REDIRECT", "CUSTOMER_RECORD_PATTERN_DETECTED"],
    ["examples/prompts/safe_prompt.txt", "ALLOW", "ACTION_ALLOW"]
  ])("scans example prompt %s", (file, action, reason) => {
    const result = scanPrompt(policy, fs.readFileSync(file, "utf8"));
    expect(result.action).toBe(action);
    expect(result.reason_codes).toContain(reason);
  });
});
