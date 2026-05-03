import type { CategoryResult, DetectorMatch } from "../models.js";

export function matchAll(text: string, regex: RegExp, ruleId: string, redacted: string): DetectorMatch[] {
  const matches: DetectorMatch[] = [];
  for (const match of text.matchAll(regex)) {
    if (match.index === undefined) continue;
    matches.push({ rule_id: ruleId, start: match.index, end: match.index + match[0].length, redacted });
  }
  return matches;
}

export function result(
  category: CategoryResult["category"],
  riskScore: number,
  confidence: CategoryResult["confidence"],
  matches: DetectorMatch[],
  reasonCodes: string[]
): CategoryResult {
  return {
    category,
    risk_score: Math.min(100, riskScore),
    confidence,
    matches,
    reason_codes: [...new Set(reasonCodes)]
  };
}

export function hasAny(text: string, regexes: RegExp[]): boolean {
  return regexes.some((regex) => regex.test(text));
}
