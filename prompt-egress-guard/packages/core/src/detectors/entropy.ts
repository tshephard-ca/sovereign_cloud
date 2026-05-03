import type { CategoryResult, DetectorMatch, ScannerPolicy } from "../models.js";
import { result } from "./utils.js";

export function detectEntropySecretCandidates(text: string, scanner: ScannerPolicy): CategoryResult {
  const matches: DetectorMatch[] = [];
  const pattern = /\b(?:key|token|secret|password|credential)\b.{0,40}\b([A-Za-z0-9+/_=-]{20,})\b/gi;
  for (const match of text.matchAll(pattern)) {
    const candidate = match[1] ?? "";
    const start = (match.index ?? 0) + match[0].indexOf(candidate);
    if (candidate.length >= scanner.min_secret_length && entropy(candidate) >= scanner.entropy_threshold) {
      matches.push({ rule_id: "secret_high_entropy_near_label", start, end: start + candidate.length, redacted: "<TOKEN_REDACTED>" });
    }
  }
  return result("secrets", 45, "MEDIUM", matches, matches.length ? ["HIGH_ENTROPY_SECRET_CANDIDATE"] : []);
}

export function entropy(value: string): number {
  const counts = new Map<string, number>();
  for (const char of value) counts.set(char, (counts.get(char) ?? 0) + 1);
  let score = 0;
  for (const count of counts.values()) {
    const p = count / value.length;
    score -= p * Math.log2(p);
  }
  return score;
}
