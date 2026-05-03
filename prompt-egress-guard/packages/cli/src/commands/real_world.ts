export {
  generateCorpusCommand as realWorldGenerateCommand,
  pilotAssessCommand as realWorldAssessCommand
} from "./pilot_runner.js";

import { generateCorpusCommand, initPilotCommand, pilotAssessCommand, pilotReportCommand, pilotRunCommand, validateCorpusCommand } from "./pilot_runner.js";

export async function realWorldRunCommand(args: Record<string, string | boolean>): Promise<number> {
  const outputDir = String(args["output-dir"] ?? args.output ?? "");
  if (!outputDir) {
    console.error("missing --output-dir");
    return 1;
  }
  await initPilotCommand({ output: outputDir, pack: args.pack ?? "developer-workstation" });
  return pilotRunCommand({
    input: `${outputDir}/input`,
    output: `${outputDir}/run`,
    policy: args.policy ?? "examples/policies/default-policy.yml"
  });
}

export { generateCorpusCommand, initPilotCommand, pilotAssessCommand, pilotReportCommand, pilotRunCommand, validateCorpusCommand };
