import { loadPolicyFile } from "@prompt-egress-guard/core";

export async function validatePolicyCommand(args: Record<string, string | boolean>): Promise<number> {
  const policyPath = String(args.policy ?? "");
  if (!policyPath) {
    console.error("missing --policy");
    return 1;
  }
  const result = loadPolicyFile(policyPath);
  console.log(JSON.stringify({ valid: result.valid, warnings: result.warnings, blockers: result.blockers }, null, 2));
  return result.valid ? 0 : 1;
}
