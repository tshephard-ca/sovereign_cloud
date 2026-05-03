import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runCli } from "../src/index.js";

describe("pilot workflow", () => {
  it("validates every example policy pack", async () => {
    const files = fs.readdirSync("examples/policy-packs").filter((file) => file.endsWith(".yml")).sort();
    expect(files.length).toBeGreaterThanOrEqual(8);
    for (const file of files) {
      expect(await runCli(["validate-policy", "--policy", path.join("examples/policy-packs", file)])).toBe(0);
    }
  });

  it("runs a focused finance pilot and writes a decision packet", async ({ task }) => {
    const dir = tmpDir(task.name);
    expect(await runCli(["init-pilot", "--pack", "finance-strict", "--output", dir])).toBe(0);
    expect(await runCli(["validate-corpus", "--input", path.join(dir, "input"), "--policy", "examples/policy-packs/finance-strict.yml"])).toBe(0);
    expect(await runCli(["pilot-run", "--policy", "examples/policy-packs/finance-strict.yml", "--input", path.join(dir, "input"), "--output", path.join(dir, "run")])).toBe(0);
    expect(await runCli(["pilot-report", "--policy", "examples/policy-packs/finance-strict.yml", "--input", path.join(dir, "input"), "--run", path.join(dir, "run"), "--output", path.join(dir, "decision_packet")])).toBe(0);

    const assessment = JSON.parse(fs.readFileSync(path.join(dir, "run", "pilot_assessment.json"), "utf8"));
    expect(assessment.output_coverage.expected_action_matches).toBe(true);
    expect(assessment.business_impact_findings.map((finding: { code: string }) => finding.code)).toContain("FINANCIAL_DATA_BLOCKED");
    expect(fs.existsSync(path.join(dir, "decision_packet", "pilot_summary.md"))).toBe(true);
    expect(fs.existsSync(path.join(dir, "decision_packet", "manifest.json"))).toBe(true);
  });

  it("explains and diffs policies for review", async ({ task }) => {
    const dir = tmpDir(task.name);
    const explanation = path.join(dir, "explain.json");
    const diff = path.join(dir, "diff.json");
    expect(await runCli(["explain-policy", "--policy", "examples/policies/default-policy.yml", "--output", explanation])).toBe(0);
    expect(await runCli(["diff-policy", "--base", "examples/policies/default-policy.yml", "--candidate", "examples/policy-packs/strict-enforcement.yml", "--output", diff])).toBe(0);

    const parsedExplanation = JSON.parse(fs.readFileSync(explanation, "utf8"));
    expect(parsedExplanation.likely_business_effect).toContain("blocks");
    expect(parsedExplanation.dnr_enabled).toBe(false);

    const parsedDiff = JSON.parse(fs.readFileSync(diff, "utf8"));
    expect(parsedDiff.category_action_changes.source_code).toEqual({ from: "REDIRECT", to: "BLOCK" });
    expect(parsedDiff.review_summary).toContain("Review whether this changes user interruption");
  });
});

function tmpDir(name: string): string {
  const dir = path.join("out", "tests", name.replace(/[^a-z0-9_-]/gi, "_"));
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
