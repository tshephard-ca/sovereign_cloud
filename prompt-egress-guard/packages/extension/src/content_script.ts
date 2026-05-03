import { type Policy } from "@prompt-egress-guard/core/browser";
import { copyPromptToClipboard, openApprovedDestination } from "./handoff.js";
import { showOverlay } from "./overlay.js";
import { installSubmitInterceptors, markConfirmedForResubmit } from "./submit_intercept.js";
import { writeLocalAudit } from "./storage.js";

declare global {
  interface Window {
    __PEG_POLICY__?: Policy;
  }
}

export function startContentScript(policy: Policy = window.__PEG_POLICY__ as Policy): void {
  if (!policy) return;
  installSubmitInterceptors(policy, document, (decision, event) => {
    if (decision.result.action === "ALLOW") return;
    void writeLocalAudit(policy, decision.result);
    showOverlay(decision.result, policy, {
      continue: () => {
        if (decision.allowResubmit && event.target) markConfirmedForResubmit(event.target);
        if (event.target instanceof HTMLFormElement) event.target.requestSubmit();
      },
      redirect: () => {
        openApprovedDestination(policy, decision.result);
        void writeLocalAudit(policy, decision.result, undefined, "redirect_opened");
      },
      copyPrompt: () => {
        void copyPromptToClipboard(policy, decision.prompt).then(() => writeLocalAudit(policy, decision.result, undefined, "clipboard_copy_requested"));
      }
    });
  });
}

if (typeof window !== "undefined" && window.__PEG_POLICY__) startContentScript(window.__PEG_POLICY__);
