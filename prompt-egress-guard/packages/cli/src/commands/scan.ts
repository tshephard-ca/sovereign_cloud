import fs from "node:fs";
import path from "node:path";
import { loadPolicyFile, scanPrompt } from "@prompt-egress-guard/core";

export async function scanCommand(args: Record<string, string | boolean>): Promise<number> {
  const policyPath = String(args.policy ?? "");
  const textFile = String(args["text-file"] ?? "");
  const output = String(args.output ?? "");
  const siteId = typeof args["site-id"] === "string" ? args["site-id"] : undefined;
  if (!policyPath || !textFile || !output) {
    console.error("missing --policy, --text-file, or --output");
    return 1;
  }
  const policyResult = loadPolicyFile(policyPath);
  if (!policyResult.valid || !policyResult.policy) {
    console.error(policyResult.blockers.join("\n"));
    return 1;
  }
  const text = fs.readFileSync(textFile, "utf8");
  const result = scanPrompt(policyResult.policy, text, { site_id: siteId });
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, `${JSON.stringify(result, null, 2)}\n`);
  return result.action === "BLOCK" || result.action === "REDIRECT" ? 2 : 0;
}
