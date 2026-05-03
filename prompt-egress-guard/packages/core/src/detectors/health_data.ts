import type { CategoryResult, DetectorMatch } from "../models.js";
import { matchAll, result } from "./utils.js";

export function detectHealthData(text: string): CategoryResult {
  const matches: DetectorMatch[] = [];
  const reasons: string[] = [];
  const identifiers = matchAll(text, /\b(?:patient_id|medical_record_number|member_id)\s*[:=]?\s*[A-Za-z0-9_.-]{4,}\b/gi, "health_patient_identifier", "<ID_REDACTED>");
  const clinical = matchAll(text, /\b(?:diagnosis|clinical note|lab result|symptoms?|treatment plan)\b/gi, "health_clinical_context", "<HEALTH_CONTEXT_REDACTED>");
  const medication = matchAll(text, /\b(?:medication|prescribed|dosage|mg twice daily)\b/gi, "health_medication_context", "<HEALTH_CONTEXT_REDACTED>");
  if (identifiers.length) {
    matches.push(...identifiers);
    reasons.push("PATIENT_IDENTIFIER_PATTERN_DETECTED");
  }
  if (clinical.length) {
    matches.push(...clinical);
    reasons.push("HEALTH_RECORD_PATTERN_DETECTED", "CLINICAL_NOTE_PATTERN_DETECTED");
  }
  if (medication.length) {
    matches.push(...medication);
    reasons.push("MEDICATION_CONTEXT_DETECTED");
  }
  return result("health_data", identifiers.length && (clinical.length || medication.length) ? 80 : 20, identifiers.length && (clinical.length || medication.length) ? "HIGH" : "LOW", matches, reasons);
}
