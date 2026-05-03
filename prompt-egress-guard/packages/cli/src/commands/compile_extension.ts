import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { loadPolicyFile } from "@prompt-egress-guard/core";
import { compileExtensionSiteConfig, contentScriptMatches, generateDnrRules, hostPermissions } from "@prompt-egress-guard/extension";

export async function compileExtensionCommand(args: Record<string, string | boolean>): Promise<number> {
  const policyPath = String(args.policy ?? "");
  const outputDir = String(args["output-dir"] ?? "");
  if (!policyPath || !outputDir) {
    console.error("missing --policy or --output-dir");
    return 1;
  }
  const policyResult = loadPolicyFile(policyPath);
  if (!policyResult.valid || !policyResult.policy) {
    console.error(policyResult.blockers.join("\n"));
    return 1;
  }
  const policy = policyResult.policy;
  fs.mkdirSync(outputDir, { recursive: true });
  const manifestTemplatePath = path.resolve(currentDir(), "../../../extension/manifest.template.json");
  const manifest = JSON.parse(fs.readFileSync(manifestTemplatePath, "utf8"));
  manifest.host_permissions = hostPermissions(policy);
  manifest.content_scripts = [
    {
      matches: contentScriptMatches(policy),
      js: ["content_script.js"],
      run_at: "document_idle"
    }
  ];
  if (!policy.dnr.enabled) {
    delete manifest.declarative_net_request;
    manifest.permissions = manifest.permissions.filter((permission: string) => permission !== "declarativeNetRequest");
  }
  fs.writeFileSync(path.join(outputDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "site_policy.json"), `${JSON.stringify(compileExtensionSiteConfig(policy), null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "dnr_rules.json"), `${JSON.stringify(generateDnrRules(policy), null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, "warning.html"), "<!doctype html><title>Prompt Egress Guard</title><p>Configured public-AI navigation was stopped by policy.</p>\n");
  const root = path.resolve(currentDir(), "../../..");
  await build({
    entryPoints: [path.join(root, "extension/src/content_script.ts"), path.join(root, "extension/src/service_worker.ts")],
    bundle: true,
    outdir: outputDir,
    format: "esm",
    platform: "browser",
    sourcemap: false,
    logLevel: "silent"
  });
  return 0;
}

function currentDir(): string {
  return path.dirname(fileURLToPath(import.meta.url));
}
