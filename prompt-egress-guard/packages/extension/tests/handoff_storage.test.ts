// @vitest-environment happy-dom
import fs from "node:fs";
import yaml from "js-yaml";
import { describe, expect, it } from "vitest";
import { PolicySchema, scanPrompt } from "@prompt-egress-guard/core";
import { buildHandoffUrl, copyPromptToClipboard, pruneEvents, writeLocalAudit, type AuditStore } from "@prompt-egress-guard/extension";

const policy = PolicySchema.parse(yaml.load(fs.readFileSync("examples/policies/default-policy.yml", "utf8")));

describe("handoff and extension audit storage", () => {
  it("handoff query string includes non-sensitive fields only", () => {
    const result = scanPrompt(policy, "```ts\nfunction sensitiveName() {}\n```");
    const url = buildHandoffUrl(policy, result);
    expect(url).toContain("policy_id=default");
    expect(url).toContain("reason_codes=");
    expect(url).not.toContain("sensitiveName");
  });

  it("clipboard copy requires explicit function call and policy allowance", async () => {
    let copied = "";
    await expect(copyPromptToClipboard(policy, "prompt text", { writeText: async (value) => { copied = value; } })).resolves.toBe("CLIPBOARD_COPY_REQUESTED");
    expect(copied).toBe("prompt text");
  });

  it("local audit write stores redacted event without raw prompt", async () => {
    const result = scanPrompt(policy, "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789");
    const store: AuditStore = { async get() { return []; }, async set(events) { expect(events[0].raw_prompt).toBeUndefined(); } };
    const event = await writeLocalAudit(policy, result, store, "blocked");
    expect(event.reason_codes).toContain("LOCAL_AUDIT_EVENT_WRITTEN");
  });

  it("audit pruning enforces max event count", () => {
    const smallPolicy = structuredClone(policy);
    smallPolicy.audit.max_events = 1;
    const now = new Date().toISOString();
    const events = [
      { event_id: "1", timestamp: now, policy_id: "default", action: "WARN", risk_score: 1, confidence: "LOW", categories: [], reason_codes: [] },
      { event_id: "2", timestamp: now, policy_id: "default", action: "BLOCK", risk_score: 90, confidence: "HIGH", categories: [], reason_codes: [] }
    ] as const;
    expect(pruneEvents([...events], smallPolicy)).toHaveLength(1);
  });
});
