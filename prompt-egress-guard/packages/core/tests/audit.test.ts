import fs from "node:fs";
import yaml from "js-yaml";
import { describe, expect, it } from "vitest";
import { createAuditEvent, PolicySchema, scanPrompt, summarizeAuditEvents } from "@prompt-egress-guard/core";

const policy = PolicySchema.parse(yaml.load(fs.readFileSync("examples/policies/default-policy.yml", "utf8")));

describe("audit", () => {
  it("excludes raw prompt by default and summarizes counts", () => {
    const result = scanPrompt(policy, "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789");
    const event = createAuditEvent(policy, result, "blocked");
    expect(event.raw_prompt).toBeUndefined();
    const summary = summarizeAuditEvents([event], true);
    expect(summary.action_counts.BLOCK).toBe(1);
    expect(summary.category_counts.secrets).toBe(1);
    expect(JSON.stringify(summary)).not.toContain("abcdefghijklmnopqrstuvwxyz");
  });
});
