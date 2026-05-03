import type { Policy, ScanResult } from "@prompt-egress-guard/core/browser";

export interface OverlayHandlers {
  continue?: () => void;
  cancel?: () => void;
  redirect?: () => void;
  copyPrompt?: () => void;
}

export function createOverlay(result: ScanResult, policy: Policy, handlers: OverlayHandlers = {}): HTMLElement {
  const root = document.createElement("div");
  root.setAttribute("data-peg-overlay", "true");
  root.style.cssText = "position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;font-family:sans-serif;";
  const panel = document.createElement("section");
  panel.style.cssText = "max-width:520px;background:white;color:#111;padding:16px;border-radius:8px;box-shadow:0 12px 40px rgba(0,0,0,.25);";
  const title = document.createElement("h2");
  title.textContent = policy.user_experience.overlay_title;
  const action = document.createElement("p");
  action.textContent = `${result.action}: ${messageForAction(result.action)}`;
  const categories = document.createElement("p");
  categories.textContent = `Categories: ${result.categories.join(", ") || "none"}`;
  const reasons = document.createElement("p");
  reasons.textContent = `Reason codes: ${result.reason_codes.join(", ")}`;
  panel.append(title, action, categories, reasons);
  if (policy.audit.store_redacted_excerpt && result.redacted_excerpt) {
    const excerpt = document.createElement("pre");
    excerpt.textContent = result.redacted_excerpt;
    excerpt.style.cssText = "white-space:pre-wrap;max-height:120px;overflow:auto;background:#f6f6f6;padding:8px;";
    panel.append(excerpt);
  }
  const controls = document.createElement("div");
  controls.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:12px;";
  if (result.action === "REDIRECT") {
    const redirect = button("Open approved endpoint", handlers.redirect);
    controls.append(redirect);
    if (policy.approved_destination?.clipboard_copy_allowed) controls.append(button("Copy prompt", handlers.copyPrompt));
  }
  if (canContinue(result, policy)) controls.append(button("Continue", handlers.continue));
  controls.append(button("Cancel", handlers.cancel));
  panel.append(controls);
  root.append(panel);
  return root;
}

export function showOverlay(result: ScanResult, policy: Policy, handlers: OverlayHandlers = {}): HTMLElement {
  const overlay = createOverlay(result, policy, {
    cancel: () => overlay.remove(),
    ...handlers
  });
  document.documentElement.append(overlay);
  return overlay;
}

function button(label: string, onClick?: () => void): HTMLButtonElement {
  const el = document.createElement("button");
  el.type = "button";
  el.textContent = label;
  el.addEventListener("click", () => onClick?.());
  return el;
}

function canContinue(result: ScanResult, policy: Policy): boolean {
  if (result.action === "WARN") return policy.user_experience.allow_continue_on_warn;
  if (result.action === "REDIRECT") return policy.user_experience.allow_continue_on_redirect;
  if (result.action === "BLOCK") return policy.user_experience.allow_continue_on_block;
  return false;
}

function messageForAction(action: ScanResult["action"]): string {
  if (action === "WARN") return "This prompt may contain sensitive information. Review before sending to a public AI site.";
  if (action === "REDIRECT") return "This prompt matches policy rules for content that should use an approved AI endpoint. The public-AI submission was stopped.";
  if (action === "BLOCK") return "This prompt matches a high-risk policy rule and cannot be sent to this configured public-AI site.";
  return "No configured rule triggered above threshold.";
}
