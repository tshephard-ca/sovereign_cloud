import fs from "node:fs";
import path from "node:path";
import { summarizeAuditEvents, type AuditEvent } from "@prompt-egress-guard/core";

export async function exportAuditCommand(args: Record<string, string | boolean>): Promise<number> {
  const auditLog = String(args["audit-log"] ?? "");
  const output = String(args.output ?? "");
  const redact = Boolean(args.redact);
  if (!auditLog || !output) {
    console.error("missing --audit-log or --output");
    return 1;
  }
  const events = fs
    .readFileSync(auditLog, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line) as AuditEvent);
  const summary = summarizeAuditEvents(events, redact);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, `${JSON.stringify(summary, null, 2)}\n`);
  return 0;
}
