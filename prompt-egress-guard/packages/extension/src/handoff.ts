import { stableHandoffId, type Policy, type ScanResult } from "@prompt-egress-guard/core/browser";

export function buildHandoffUrl(policy: Policy, result: ScanResult): string {
  const destination = policy.approved_destination;
  if (!destination?.url) throw new Error("APPROVED_DESTINATION_MISSING");
  const url = new URL(destination.url);
  const handoffId = stableHandoffId(result.prompt_hash, policy.policy_id);
  if (destination.include_handoff_id) url.searchParams.set("handoff_id", handoffId);
  url.searchParams.set("policy_id", policy.policy_id);
  url.searchParams.set("action", result.action);
  if (destination.include_reason_codes) url.searchParams.set("reason_codes", result.reason_codes.join(","));
  return url.toString();
}

export function openApprovedDestination(policy: Policy, result: ScanResult, opener: (url: string) => void = (url) => globalThis.open?.(url, "_blank")): string {
  const url = buildHandoffUrl(policy, result);
  opener(url);
  return url;
}

export async function copyPromptToClipboard(policy: Policy, prompt: string, clipboard: Pick<Clipboard, "writeText"> = navigator.clipboard): Promise<string> {
  if (!policy.approved_destination?.clipboard_copy_allowed) throw new Error("CLIPBOARD_COPY_NOT_ALLOWED");
  await clipboard.writeText(prompt);
  return "CLIPBOARD_COPY_REQUESTED";
}
