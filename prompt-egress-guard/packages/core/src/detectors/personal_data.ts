import type { CategoryResult, DetectorMatch } from "../models.js";
import { matchAll, result } from "./utils.js";

export function detectPersonalData(text: string): CategoryResult {
  const matches: DetectorMatch[] = [];
  const reasons: string[] = [];
  add(matches, reasons, matchAll(text, /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "personal_email", "<EMAIL_REDACTED>"), "EMAIL_ADDRESS_DETECTED");
  add(matches, reasons, matchAll(text, /(?:\+?\d[\d .()-]{7,}\d)/g, "personal_phone", "<PHONE_REDACTED>"), "PHONE_NUMBER_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:date of birth|dob)\s*[:=]?\s*\d{4}-\d{2}-\d{2}\b/gi, "personal_dob", "<ID_REDACTED>"), "DOB_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b\d{3,5}\s+[A-Z][A-Za-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)\b/g, "personal_address", "<ID_REDACTED>"), "ADDRESS_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:national_id|identity_number)\s*[:=]?\s*[A-Za-z0-9-]{6,}\b/gi, "personal_national_id_candidate", "<ID_REDACTED>"), "NATIONAL_ID_CANDIDATE_DETECTED");
  const score = reasons.length >= 2 ? 25 : reasons.length ? 15 : 0;
  return result("personal_data", score, reasons.length >= 2 ? "MEDIUM" : "LOW", matches, reasons);
}

function add(matches: DetectorMatch[], reasons: string[], found: DetectorMatch[], reason: string): void {
  if (found.length) {
    matches.push(...found);
    reasons.push(reason);
  }
}
