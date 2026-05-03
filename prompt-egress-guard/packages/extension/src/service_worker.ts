export async function getLocalAuditSummary(): Promise<{ event_count: number }> {
  const storage = (globalThis as unknown as { chrome?: any }).chrome?.storage?.local;
  if (!storage) return { event_count: 0 };
  const value = await storage.get("prompt_egress_guard_audit");
  return { event_count: (value.prompt_egress_guard_audit ?? []).length };
}
