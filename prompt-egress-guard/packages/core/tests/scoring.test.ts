import fs from "node:fs";
import yaml from "js-yaml";
import { describe, expect, it } from "vitest";
import { PolicySchema, scanPrompt } from "@prompt-egress-guard/core";

const policy = PolicySchema.parse(yaml.load(fs.readFileSync("examples/policies/default-policy.yml", "utf8")));

describe("scoring and decisions", () => {
  it("returns ALLOW for safe prompt", () => {
    expect(scanPrompt(policy, "Summarize this public announcement.").action).toBe("ALLOW");
  });

  it("returns WARN for low-risk personal data", () => {
    expect(scanPrompt(policy, "Contact me at taylor@example.invalid").action).toBe("WARN");
  });

  it("returns REDIRECT for source-code-like prompt", () => {
    expect(scanPrompt(policy, "```ts\nfunction work() { return 1 }\n```").action).toBe("REDIRECT");
  });

  it("returns BLOCK for secrets", () => {
    expect(scanPrompt(policy, "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789").action).toBe("BLOCK");
  });

  it("category action overrides numeric threshold upward", () => {
    const strictThresholdPolicy = structuredClone(policy);
    strictThresholdPolicy.actions.thresholds.warn_score = 90;
    strictThresholdPolicy.actions.thresholds.redirect_score = 95;
    strictThresholdPolicy.actions.thresholds.block_score = 99;
    expect(scanPrompt(strictThresholdPolicy, "def helper():\n    return 1").action).toBe("REDIRECT");
  });
});
