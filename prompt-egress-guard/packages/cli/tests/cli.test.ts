import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runCli } from "../src/index.js";

describe("CLI", () => {
  it("validate-policy exits success for default policy", async () => {
    await expect(runCli(["validate-policy", "--policy", "examples/policies/default-policy.yml"])).resolves.toBe(0);
  });

  it("validate-policy exits failure for unsafe policy", async ({ task }) => {
    const dir = tmpDir(task.name);
    const policy = fs.readFileSync("examples/policies/default-policy.yml", "utf8").replace("include_prompt: false", "include_prompt: true");
    const file = path.join(dir, "unsafe.yml");
    fs.writeFileSync(file, policy);
    await expect(runCli(["validate-policy", "--policy", file])).resolves.toBe(1);
  });

  it("scan exits 0 for ALLOW", async ({ task }) => {
    const dir = tmpDir(task.name);
    const output = path.join(dir, "scan.json");
    const code = await runCli(["scan", "--policy", "examples/policies/default-policy.yml", "--text-file", "examples/prompts/safe_prompt.txt", "--output", output]);
    expect(code).toBe(0);
    expect(JSON.parse(fs.readFileSync(output, "utf8")).action).toBe("ALLOW");
  });

  it("scan exits 2 for REDIRECT or BLOCK and output schema is stable", async ({ task }) => {
    const dir = tmpDir(task.name);
    const output = path.join(dir, "scan.json");
    const code = await runCli(["scan", "--policy", "examples/policies/default-policy.yml", "--text-file", "examples/prompts/source_code_prompt.txt", "--output", output]);
    const parsed = JSON.parse(fs.readFileSync(output, "utf8"));
    expect(code).toBe(2);
    expect(parsed).toMatchObject({ policy_id: "default", action: "REDIRECT", risk_status: "REDIRECT" });
    expect(parsed.reason_codes).toContain("SOURCE_CODE_PATTERN_DETECTED");
    expect(parsed.redacted_excerpt).not.toContain("runJob");
  });

  it("compile-extension writes manifest, site policy JSON, and DNR rules", async ({ task }) => {
    const dir = tmpDir(task.name);
    const code = await runCli(["compile-extension", "--policy", "examples/policies/default-policy.yml", "--output-dir", dir]);
    expect(code).toBe(0);
    const manifest = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
    expect(manifest.host_permissions).toHaveLength(5);
    expect(manifest.host_permissions).not.toContain("<all_urls>");
    expect(manifest.permissions).not.toContain("declarativeNetRequest");
    expect(manifest.declarative_net_request).toBeUndefined();
    expect(JSON.parse(fs.readFileSync(path.join(dir, "site_policy.json"), "utf8")).sites).toHaveLength(5);
    expect(JSON.parse(fs.readFileSync(path.join(dir, "dnr_rules.json"), "utf8"))).toHaveLength(0);
  });

  it("export-audit produces deterministic redacted summary", async ({ task }) => {
    const dir = tmpDir(task.name);
    const outputA = path.join(dir, "summary-a.json");
    const outputB = path.join(dir, "summary-b.json");
    expect(await runCli(["export-audit", "--audit-log", "examples/audit/local_audit.jsonl", "--output", outputA, "--redact"])).toBe(0);
    expect(await runCli(["export-audit", "--audit-log", "examples/audit/local_audit.jsonl", "--output", outputB, "--redact"])).toBe(0);
    const summary = JSON.parse(fs.readFileSync(outputA, "utf8"));
    expect(summary.event_count).toBe(2);
    expect(summary.action_counts).toEqual({ BLOCK: 1, REDIRECT: 1 });
    expect(fs.readFileSync(outputA, "utf8")).toBe(fs.readFileSync(outputB, "utf8"));
    expect(fs.readFileSync(outputA, "utf8")).not.toContain("raw_prompt");
  });
});

function tmpDir(name: string): string {
  const dir = path.join("out", "tests", name.replace(/[^a-z0-9_-]/gi, "_"));
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
