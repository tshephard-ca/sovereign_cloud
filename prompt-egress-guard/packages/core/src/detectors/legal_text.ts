import type { CategoryResult, DetectorMatch } from "../models.js";
import { matchAll, result } from "./utils.js";

export function detectLegalText(text: string): CategoryResult {
  const matches: DetectorMatch[] = [];
  const reasons: string[] = [];
  add(matches, reasons, matchAll(text, /\b(?:privileged and confidential|attorney-client|solicitor-client|legal advice)\b/gi, "legal_privilege_candidate", "<LEGAL_TEXT_REDACTED>"), "LEGAL_PRIVILEGE_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:settlement agreement|draft contract|agreement between|whereas)\b/gi, "legal_contract_candidate", "<CONTRACT_TEXT_REDACTED>"), "CONTRACT_DRAFT_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:litigation strategy|court file number|case caption|motion for)\b/gi, "legal_litigation_context", "<LEGAL_TEXT_REDACTED>"), "LITIGATION_CONTEXT_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:matter number|matter_id)\s*[:=]?\s*[A-Za-z0-9_.-]{4,}\b/gi, "legal_matter_identifier", "<ID_REDACTED>"), "MATTER_IDENTIFIER_PATTERN_DETECTED");
  return result("legal_text", reasons.length ? 50 : 0, reasons.length > 1 ? "MEDIUM" : "LOW", matches, reasons);
}

function add(matches: DetectorMatch[], reasons: string[], found: DetectorMatch[], reason: string): void {
  if (found.length) {
    matches.push(...found);
    reasons.push(reason);
  }
}
