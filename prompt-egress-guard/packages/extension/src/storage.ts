import { createAuditEvent, type AuditEvent, type Policy, type ScanResult } from "@prompt-egress-guard/core/browser";

export interface AuditStore {
  get(): Promise<AuditEvent[]>;
  set(events: AuditEvent[]): Promise<void>;
}

export function browserLocalAuditStore(key = "prompt_egress_guard_audit"): AuditStore {
  return {
    async get() {
      const storage = (globalThis as unknown as { chrome?: any }).chrome?.storage?.local;
      if (!storage) return [];
      const value = await storage.get(key);
      return value[key] ?? [];
    },
    async set(events) {
      const storage = (globalThis as unknown as { chrome?: any }).chrome?.storage?.local;
      if (storage) await storage.set({ [key]: events });
    }
  };
}

export async function writeLocalAudit(policy: Policy, result: ScanResult, store: AuditStore = browserLocalAuditStore(), userDecision?: string): Promise<AuditEvent> {
  const events = await store.get();
  const next = pruneEvents([...events, createAuditEvent(policy, result, userDecision)], policy);
  await store.set(next);
  return next[next.length - 1];
}

export function pruneEvents(events: AuditEvent[], policy: Policy): AuditEvent[] {
  const maxAgeMs = policy.audit.retention_days * 24 * 60 * 60 * 1000;
  const cutoff = Date.now() - maxAgeMs;
  return events
    .filter((event) => Date.parse(event.timestamp) >= cutoff)
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
    .slice(-policy.audit.max_events);
}
