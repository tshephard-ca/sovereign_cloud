#!/usr/bin/env node
import { compileExtensionCommand } from "./commands/compile_extension.js";
import { exportAuditCommand } from "./commands/export_audit.js";
import {
  generateCorpusCommand,
  initPilotCommand,
  pilotAssessCommand,
  pilotReportCommand,
  pilotRunCommand,
  realWorldAssessCommand,
  realWorldGenerateCommand,
  realWorldRunCommand,
  validateCorpusCommand
} from "./commands/real_world.js";
import { diffPolicyCommand, explainPolicyCommand } from "./commands/policy_review.js";
import { scanCommand } from "./commands/scan.js";
import { validatePolicyCommand } from "./commands/validate_policy.js";

type Args = Record<string, string | boolean>;

export async function runCli(argv = process.argv.slice(2)): Promise<number> {
  const [command, ...rest] = argv;
  const args = parseArgs(rest);
  try {
    if (command === "validate-policy") return await validatePolicyCommand(args);
    if (command === "scan") return await scanCommand(args);
    if (command === "compile-extension") return await compileExtensionCommand(args);
    if (command === "export-audit") return await exportAuditCommand(args);
    if (command === "init-pilot") return await initPilotCommand(args);
    if (command === "generate-corpus") return await generateCorpusCommand(args);
    if (command === "validate-corpus") return await validateCorpusCommand(args);
    if (command === "pilot-run") return await pilotRunCommand(args);
    if (command === "pilot-report") return await pilotReportCommand(args);
    if (command === "pilot-assess") return await pilotAssessCommand(args);
    if (command === "explain-policy") return await explainPolicyCommand(args);
    if (command === "diff-policy") return await diffPolicyCommand(args);
    if (command === "real-world-generate") return await realWorldGenerateCommand(args);
    if (command === "real-world-run") return await realWorldRunCommand(args);
    if (command === "real-world-assess") return await realWorldAssessCommand(args);
    console.error(`unknown command: ${command ?? ""}`);
    return 1;
  } catch (error) {
    console.error((error as Error).message);
    return 1;
  }
}

export function parseArgs(argv: string[]): Args {
  const output: Args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      output[key] = true;
    } else {
      output[key] = next;
      index += 1;
    }
  }
  return output;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  runCli().then((code) => {
    process.exitCode = code;
  });
}
