import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { parseArgs, runCli } from "../src/index.js";

describe("additional CLI behavior", () => {
  it("parseArgs handles boolean flags deterministically", () => {
    expect(parseArgs(["--policy", "p.yml", "--redact"])).toEqual({ policy: "p.yml", redact: true });
  });

  it("scan output does not store raw prompt text", async ({ task }) => {
    const dir = tmpDir(task.name);
    const output = path.join(dir, "secret-scan.json");
    await runCli(["scan", "--policy", "examples/policies/default-policy.yml", "--text-file", "examples/prompts/secrets_prompt.txt", "--output", output]);
    const raw = fs.readFileSync(output, "utf8");
    expect(raw).toContain("<TOKEN_REDACTED>");
    expect(raw).not.toContain("abcdefghijklmnopqrstuvwxyz0123456789");
  });

  it("unknown command exits with runtime error code", async () => {
    await expect(runCli(["unknown-command"])).resolves.toBe(1);
  });

  it("compile-extension writes bundled content script and service worker", async ({ task }) => {
    const dir = tmpDir(task.name);
    expect(await runCli(["compile-extension", "--policy", "examples/policies/default-policy.yml", "--output-dir", dir])).toBe(0);
    expect(fs.existsSync(path.join(dir, "content_script.js"))).toBe(true);
    expect(fs.existsSync(path.join(dir, "service_worker.js"))).toBe(true);
  });
});

function tmpDir(name: string): string {
  const dir = path.join("out", "tests", name.replace(/[^a-z0-9_-]/gi, "_"));
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
