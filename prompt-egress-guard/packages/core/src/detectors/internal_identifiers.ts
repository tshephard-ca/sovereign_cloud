import type { CategoryResult, DetectorMatch } from "../models.js";
import { matchAll, result } from "./utils.js";

export function detectInternalIdentifiers(text: string): CategoryResult {
  const matches: DetectorMatch[] = [];
  const reasons: string[] = [];
  add(matches, reasons, matchAll(text, /\b(?:employee_id|asset_id|project_codename|internal_ticket)\s*[:=]?\s*[A-Za-z0-9_.-]{3,}\b/gi, "internal_labeled_identifier", "<ID_REDACTED>"), "INTERNAL_IDENTIFIER_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b/g, "internal_private_ip", "<ID_REDACTED>"), "PRIVATE_IP_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b[a-z0-9-]+(?:\.internal|\.corp|\.lan|\.local)\b/gi, "internal_hostname", "<ID_REDACTED>"), "INTERNAL_HOSTNAME_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:INT|OPS|SEC|BUG|INC)-\d{3,}\b/g, "internal_ticket", "<ID_REDACTED>"), "INTERNAL_TICKET_PATTERN_DETECTED");
  const envNearHost = /\b(?:prod|staging|dev)\b.{0,50}\b[a-z0-9-]+(?:\.internal|\.corp|\.lan|\.local)\b/i.exec(text);
  if (envNearHost?.index !== undefined) {
    matches.push({ rule_id: "internal_environment_hostname", start: envNearHost.index, end: envNearHost.index + envNearHost[0].length, redacted: "<ID_REDACTED>" });
    reasons.push("INTERNAL_HOSTNAME_PATTERN_DETECTED");
  }
  return result("internal_identifiers", matches.length ? 15 : 0, matches.length > 1 ? "MEDIUM" : "LOW", matches, reasons);
}

function add(matches: DetectorMatch[], reasons: string[], found: DetectorMatch[], reason: string): void {
  if (found.length) {
    matches.push(...found);
    reasons.push(reason);
  }
}
