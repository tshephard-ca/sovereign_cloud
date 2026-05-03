import type { CategoryResult, ScannerPolicy } from "../models.js";
import { detectCustomerRecords } from "./customer_records.js";
import { detectEntropySecretCandidates } from "./entropy.js";
import { detectFinancialData } from "./financial_data.js";
import { detectHealthData } from "./health_data.js";
import { detectInternalIdentifiers } from "./internal_identifiers.js";
import { detectLegalText } from "./legal_text.js";
import { detectPersonalData } from "./personal_data.js";
import { detectSecrets } from "./secrets.js";
import { detectSourceCode } from "./source_code.js";

export { detectCustomerRecords } from "./customer_records.js";
export { detectEntropySecretCandidates } from "./entropy.js";
export { detectFinancialData } from "./financial_data.js";
export { detectHealthData } from "./health_data.js";
export { detectInternalIdentifiers } from "./internal_identifiers.js";
export { detectLegalText } from "./legal_text.js";
export { detectPersonalData } from "./personal_data.js";
export { detectSecrets } from "./secrets.js";
export { detectSourceCode } from "./source_code.js";

export function runDetectors(text: string, scanner: ScannerPolicy): CategoryResult[] {
  const results = [
    detectSecrets(text, scanner),
    detectSourceCode(text),
    detectCustomerRecords(text),
    detectHealthData(text),
    detectLegalText(text),
    detectInternalIdentifiers(text),
    detectPersonalData(text),
    detectFinancialData(text)
  ].filter((result): result is CategoryResult => result.matches.length > 0);

  const entropy = detectEntropySecretCandidates(text, scanner);
  if (entropy.matches.length > 0) {
    const existing = results.find((result) => result.category === "secrets");
    if (existing) {
      existing.matches.push(...entropy.matches);
      existing.reason_codes = [...new Set([...existing.reason_codes, ...entropy.reason_codes])];
      existing.risk_score = Math.min(100, existing.risk_score + entropy.risk_score);
      existing.confidence = existing.confidence === "HIGH" ? "HIGH" : entropy.confidence;
    } else {
      results.unshift(entropy);
    }
  }
  return results;
}

export * from "./utils.js";
