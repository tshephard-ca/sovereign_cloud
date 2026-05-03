import { scanPrompt, type Policy, type ScanResult } from "@prompt-egress-guard/core/browser";
import { capturePrompt } from "./dom_capture.js";
import { monitoredSiteForUrl } from "./extension_policy.js";

export interface SubmitDecision {
  prevented: boolean;
  allowResubmit: boolean;
  result: ScanResult;
  prompt: string;
}

const confirmedElements = new WeakSet<EventTarget>();

export function evaluateSubmitAttempt(policy: Policy, siteId: string, prompt: string, extraWarnings: string[] = []): SubmitDecision {
  const result = scanPrompt(policy, prompt, { site_id: siteId });
  result.warnings = [...new Set([...result.warnings, ...extraWarnings])];
  const prevented = result.action === "BLOCK" || result.action === "REDIRECT" || result.action === "WARN";
  return { prevented, allowResubmit: result.action === "WARN" && policy.user_experience.allow_continue_on_warn, result, prompt };
}

export function installSubmitInterceptors(policy: Policy, documentRef: Document = document, onDecision: (decision: SubmitDecision, event: Event) => void): void {
  const site = monitoredSiteForUrl(policy, documentRef.location?.href ?? "") ?? policy.monitored_sites[0];
  if (!site) return;
  documentRef.addEventListener(
    "submit",
    (event) => {
      if (confirmedElements.has(event.target as EventTarget)) {
        confirmedElements.delete(event.target as EventTarget);
        return;
      }
      const captured = capturePrompt(documentRef, site, documentRef.activeElement, event.target as Element);
      const decision = evaluateSubmitAttempt(policy, site.site_id, captured.prompt, captured.warnings);
      if (decision.prevented) event.preventDefault();
      onDecision(decision, event);
    },
    true
  );
  documentRef.addEventListener(
    "click",
    (event) => {
      const target = event.target instanceof Element ? event.target : undefined;
      if (!target || !matchesSubmitSelector(target, site.submit_selectors)) return;
      const captured = capturePrompt(documentRef, site, documentRef.activeElement, target);
      const decision = evaluateSubmitAttempt(policy, site.site_id, captured.prompt, captured.warnings);
      if (decision.prevented) event.preventDefault();
      onDecision(decision, event);
    },
    true
  );
  documentRef.addEventListener(
    "keydown",
    (event) => {
      const keyboard = site.keyboard_submit;
      const keyEvent = event as KeyboardEvent;
      const shouldSubmit = keyEvent.key === "Enter" && ((keyboard.ctrl_enter && keyEvent.ctrlKey) || (keyboard.cmd_enter && keyEvent.metaKey) || (keyboard.plain_enter && !keyEvent.ctrlKey && !keyEvent.metaKey));
      if (!shouldSubmit) return;
      const captured = capturePrompt(documentRef, site, documentRef.activeElement, event.target as Element);
      const decision = evaluateSubmitAttempt(policy, site.site_id, captured.prompt, captured.warnings);
      if (decision.prevented) event.preventDefault();
      onDecision(decision, event);
    },
    true
  );
}

export function markConfirmedForResubmit(target: EventTarget): void {
  confirmedElements.add(target);
}

function matchesSubmitSelector(target: Element, selectors: string[]): boolean {
  return selectors.some((selector) => {
    try {
      return target.matches(selector) || Boolean(target.closest(selector));
    } catch {
      return false;
    }
  });
}
