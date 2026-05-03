import type { AuditEvent, Policy, ScanResult } from "./models.js";
import { promptHash } from "./redaction.js";

export function createAuditEvent(policy: Policy, result: ScanResult, userDecision?: string): AuditEvent {
  const event: AuditEvent = {
    event_id: randomId(),
    timestamp: new Date().toISOString(),
    policy_id: policy.policy_id,
    action: result.action,
    risk_score: result.risk_score,
    confidence: result.confidence,
    categories: result.categories,
    reason_codes: [...new Set([...result.reason_codes, "LOCAL_AUDIT_EVENT_WRITTEN"])],
    user_decision: userDecision
  };
  if (policy.audit.store_site_id) event.site_id = result.site_id;
  if (policy.audit.store_prompt_hash) event.prompt_hash = result.prompt_hash;
  if (policy.audit.store_redacted_excerpt) event.redacted_excerpt = result.redacted_excerpt;
  if (policy.audit.store_raw_prompt && policy.audit.unsafe_audit_storage_acknowledgement) {
    event.raw_prompt = undefined;
  }
  if (result.action === "REDIRECT") event.handoff_id = stableHandoffId(result.prompt_hash, result.policy_id);
  return event;
}

export interface AuditSummary {
  event_count: number;
  action_counts: Record<string, number>;
  category_counts: Record<string, number>;
  reason_code_counts: Record<string, number>;
  first_event_time: string | null;
  last_event_time: string | null;
  warnings: string[];
}

export function summarizeAuditEvents(events: AuditEvent[], redact = true): AuditSummary {
  const sorted = [...events].sort((a, b) => a.timestamp.localeCompare(b.timestamp) || a.event_id.localeCompare(b.event_id));
  const actionCounts: Record<string, number> = {};
  const categoryCounts: Record<string, number> = {};
  const reasonCounts: Record<string, number> = {};
  for (const event of sorted) {
    actionCounts[event.action] = (actionCounts[event.action] ?? 0) + 1;
    for (const category of event.categories) categoryCounts[category] = (categoryCounts[category] ?? 0) + 1;
    for (const reason of event.reason_codes) reasonCounts[reason] = (reasonCounts[reason] ?? 0) + 1;
    if (redact) delete (event as Partial<AuditEvent>).raw_prompt;
  }
  return {
    event_count: sorted.length,
    action_counts: ordered(actionCounts),
    category_counts: ordered(categoryCounts),
    reason_code_counts: ordered(reasonCounts),
    first_event_time: sorted[0]?.timestamp ?? null,
    last_event_time: sorted.at(-1)?.timestamp ?? null,
    warnings: ["REVIEW_ONLY_AUDIT_EXPORT"]
  };
}

export function stableHandoffId(promptHashValue: string, policyId: string): string {
  return `handoff_${promptHash(`${policyId}:${promptHashValue}`, 12)}`;
}

function randomId(): string {
  const cryptoObject = globalThis.crypto as Crypto | undefined;
  if (cryptoObject?.randomUUID) return cryptoObject.randomUUID();
  return `evt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function ordered(input: Record<string, number>): Record<string, number> {
  return Object.fromEntries(Object.entries(input).sort(([a], [b]) => a.localeCompare(b)));
}
