import type { CategoryResult, DetectorMatch, ScannerPolicy } from "../models.js";
import { matchAll, result } from "./utils.js";

export function detectSecrets(text: string, scanner: ScannerPolicy): CategoryResult {
  const matches: DetectorMatch[] = [];
  const reasons: string[] = [];

  add(matches, reasons, matchAll(text, /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/gi, "secret_private_key_block", "<PRIVATE_KEY_REDACTED>"), "PRIVATE_KEY_BLOCK_DETECTED");
  add(matches, reasons, matchAll(text, /\bAuthorization:\s*Bearer\s+[A-Za-z0-9._~+/-]{20,}=*/gi, "secret_bearer_authorization", "Authorization: Bearer <TOKEN_REDACTED>"), "BEARER_TOKEN_DETECTED");
  add(matches, reasons, matchAll(text, /\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*/gi, "secret_bearer_token", "bearer <TOKEN_REDACTED>"), "BEARER_TOKEN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:api_key|apikey|secret_key|access_token|refresh_token|client_secret)\s*[:=]\s*["']?[A-Za-z0-9._~+/-]{12,}["']?/gi, "secret_key_assignment", "<SECRET_REDACTED>"), "API_KEY_PATTERN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:connection|string|database|db)[\s\S]{0,60}(?:password|pwd)=([^;\s&]{6,})/gi, "secret_connection_password", "<CONNECTION_STRING_REDACTED>"), "CONNECTION_STRING_SECRET_DETECTED");
  add(matches, reasons, matchAll(text, /\b[a-z][a-z0-9+.-]+:\/\/[^:\s/@]+:[^@\s/]+@[^ \n\r]+/gi, "secret_database_url_credentials", "<CONNECTION_STRING_REDACTED>"), "CONNECTION_STRING_SECRET_DETECTED");
  add(matches, reasons, matchAll(text, /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, "secret_jwt_like", "<TOKEN_REDACTED>"), "JWT_LIKE_TOKEN_DETECTED");
  add(matches, reasons, matchAll(text, /\b(?:access_key|public_key_id)\s*[:=]\s*[A-Z0-9]{16,}\b/gi, "secret_generic_access_key_shape", "<SECRET_REDACTED>"), "API_KEY_PATTERN_DETECTED");

  const strong = reasons.some((reason) => reason !== "HIGH_ENTROPY_SECRET_CANDIDATE");
  return result("secrets", strong ? 90 : 40, strong ? "HIGH" : "MEDIUM", matches, reasons);
}

function add(matches: DetectorMatch[], reasons: string[], found: DetectorMatch[], reason: string): void {
  if (found.length === 0) return;
  matches.push(...found);
  reasons.push(reason);
}
