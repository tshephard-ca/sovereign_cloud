import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runCli } from "../src/index.js";

describe("real-world data generator and assessment", () => {
  it("generates full-coverage prompt data and assesses zero gaps", async ({ task }) => {
    const dir = path.join("out", "tests", task.name.replace(/[^a-z0-9_-]/gi, "_"));
    fs.rmSync(dir, { recursive: true, force: true });
    const code = await runCli(["real-world-run", "--policy", "examples/policies/default-policy.yml", "--output-dir", dir]);
    expect(code).toBe(0);
    const assessment = JSON.parse(fs.readFileSync(path.join(dir, "run", "real_world_assessment.json"), "utf8"));
    expect(assessment.status).toBe("PASS");
    expect(assessment.input_gaps).toEqual([]);
    expect(assessment.output_gaps).toEqual([]);
    expect(assessment.input_coverage.category_count).toBe(8);
    expect(assessment.input_coverage.action_count).toBe(4);
    expect(assessment.input_coverage.has_truncation_case).toBe(true);
    expect(assessment.output_coverage.has_business_impact_report).toBe(true);
    expect(assessment.output_coverage.raw_secret_absent_from_scan_output).toBe(true);
    expect(assessment.business_impact_findings.length).toBeGreaterThanOrEqual(8);
  });
});
