import type { CategoryResult, DetectorMatch } from "../models.js";
import { looksLikePaymentCard } from "../redaction.js";
import { matchAll, result } from "./utils.js";

export function detectFinancialData(text: string): CategoryResult {
  const matches: DetectorMatch[] = [];
  const reasons: string[] = [];
  for (const match of text.matchAll(/\b(?:\d[ -]*?){13,19}\b/g)) {
    if (match.index !== undefined && looksLikePaymentCard(match[0])) {
      matches.push({ rule_id: "financial_payment_card_luhn", start: match.index, end: match.index + match[0].length, redacted: "<PAYMENT_CARD_REDACTED>" });
      reasons.push("PAYMENT_CARD_CANDIDATE_DETECTED");
    }
  }
  add(matches, reasons, matchAll(text, /\b(?:bank_account|routing_number|iban|account number)\s*[:=]?\s*[A-Za-z0-9 -]{6,}\b/gi, "financial_bank_account", "<ID_REDACTED>"), "BANK_ACCOUNT_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:payroll|salary file|direct deposit)\b/gi, "financial_payroll_context", "<FINANCIAL_TEXT_REDACTED>"), "PAYROLL_CONTEXT_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:tax_id|tax identifier)\s*[:=]?\s*[A-Za-z0-9-]{6,}\b/gi, "financial_tax_identifier", "<ID_REDACTED>"), "TAX_IDENTIFIER_CANDIDATE_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:payment_secret|payment_token|gateway_secret)\s*[:=]\s*[A-Za-z0-9._~+/-]{12,}\b/gi, "financial_payment_secret", "<SECRET_REDACTED>"), "PAYMENT_SECRET_PATTERN_DETECTED");
  return result("financial_data", reasons.length ? 80 : 0, reasons.includes("PAYMENT_CARD_CANDIDATE_DETECTED") || reasons.includes("PAYMENT_SECRET_PATTERN_DETECTED") ? "HIGH" : "MEDIUM", matches, reasons);
}

function add(matches: DetectorMatch[], reasons: string[], found: DetectorMatch[], reason: string): void {
  if (found.length) {
    matches.push(...found);
    reasons.push(reason);
  }
}
