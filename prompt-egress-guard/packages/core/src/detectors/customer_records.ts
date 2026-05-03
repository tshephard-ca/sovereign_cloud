import type { CategoryResult, DetectorMatch } from "../models.js";
import { matchAll, result } from "./utils.js";

export function detectCustomerRecords(text: string): CategoryResult {
  const matches: DetectorMatch[] = [];
  const reasons: string[] = [];
  const idMatches = matchAll(text, /\b(?:customer_id|client_id|account_id|customer number|account number)\s*[:=]?\s*[A-Za-z0-9_.-]{4,}\b/gi, "customer_labeled_identifier", "<ID_REDACTED>");
  const ticketMatches = matchAll(text, /\b(?:support ticket|case ticket|ticket_id|case_id)\s*[:=]?\s*[A-Za-z0-9_.-]{4,}\b/gi, "customer_support_ticket", "<ID_REDACTED>");
  const contactCombo = /[A-Z][a-z]+ [A-Z][a-z]+[\s\S]{0,80}[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}[\s\S]{0,80}\b(?:account|customer|client)\b/i;
  if (idMatches.length) {
    matches.push(...idMatches);
    reasons.push("ACCOUNT_IDENTIFIER_PATTERN_DETECTED", "CUSTOMER_RECORD_PATTERN_DETECTED");
  }
  if (ticketMatches.length) {
    matches.push(...ticketMatches);
    reasons.push("SUPPORT_TICKET_PATTERN_DETECTED");
  }
  const contact = contactCombo.exec(text);
  if (contact?.index !== undefined) {
    matches.push({ rule_id: "customer_contact_combination", start: contact.index, end: contact.index + contact[0].length, redacted: "<CUSTOMER_CONTACT_REDACTED>" });
    reasons.push("CUSTOMER_CONTACT_COMBINATION_DETECTED");
  }
  return result("customer_records", reasons.length >= 2 ? 50 : 0, reasons.length >= 2 ? "MEDIUM" : "LOW", matches, reasons);
}
