// @vitest-environment happy-dom
import fs from "node:fs";
import yaml from "js-yaml";
import { describe, expect, it, vi } from "vitest";
import { PolicySchema } from "@prompt-egress-guard/core";
import { buildHandoffUrl, createOverlay, evaluateSubmitAttempt, generateDnrRules, hostPermissions, installSubmitInterceptors, monitoredSiteForUrl } from "@prompt-egress-guard/extension";

const policy = PolicySchema.parse(yaml.load(fs.readFileSync("examples/policies/default-policy.yml", "utf8")));

describe("submit interception", () => {
  it("scans active prompt on submit and blocks high-risk content", () => {
    const decision = evaluateSubmitAttempt(policy, "public_ai_1", "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789");
    expect(decision.prevented).toBe(true);
    expect(decision.result.action).toBe("BLOCK");
  });

  it("Ctrl+Enter submit path scans prompt when configured", () => {
    document.body.innerHTML = "<textarea>def helper():\n    return 1</textarea>";
    const spy = vi.fn();
    installSubmitInterceptors(policy, document, spy);
    const event = new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true, cancelable: true });
    document.querySelector("textarea")!.dispatchEvent(event);
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls[0][0].result.action).toBe("REDIRECT");
  });

  it("WARN prevents initial submit and allows one confirmed resubmit decision", () => {
    const decision = evaluateSubmitAttempt(policy, "public_ai_1", "email taylor@example.invalid");
    expect(decision.result.action).toBe("WARN");
    expect(decision.prevented).toBe(true);
    expect(decision.allowResubmit).toBe(true);
  });

  it("REDIRECT prevents submit and builds approved handoff without raw prompt", () => {
    const decision = evaluateSubmitAttempt(policy, "public_ai_1", "```ts\nfunction x(){}\n```");
    const url = buildHandoffUrl(policy, decision.result);
    expect(decision.prevented).toBe(true);
    expect(url).toContain("handoff_id=");
    expect(url).not.toContain("function");
  });

  it("BLOCK prevents submit", () => {
    expect(evaluateSubmitAttempt(policy, "public_ai_1", "patient_id: PT-1 diagnosis: fever").prevented).toBe(true);
  });
});

describe("overlay and extension config", () => {
  it("overlay shows reason codes and no raw prompt by default", () => {
    const decision = evaluateSubmitAttempt(policy, "public_ai_1", "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789");
    const overlay = createOverlay(decision.result, policy);
    expect(overlay.textContent).toContain("BEARER_TOKEN_DETECTED");
    expect(overlay.textContent).not.toContain("abcdefghijklmnopqrstuvwxyz");
  });

  it("clipboard copy is represented as an explicit button only when policy allows it", () => {
    const decision = evaluateSubmitAttempt(policy, "public_ai_1", "```ts\nfunction x(){}\n```");
    const overlay = createOverlay(decision.result, policy);
    expect(overlay.textContent).toContain("Copy prompt");
  });

  it("DNR rules and manifest host permissions come only from policy domains", () => {
    const rules = generateDnrRules({ ...policy, dnr: { ...policy.dnr, enabled: true } });
    expect(generateDnrRules(policy)).toHaveLength(0);
    expect(rules).toHaveLength(5);
    expect(rules[0].condition.urlFilter).toBe("public-ai-1.example.invalid");
    expect(hostPermissions(policy)).toEqual(policy.monitored_sites.map((site) => site.host_permissions[0]).sort());
    expect(hostPermissions(policy)).not.toContain("<all_urls>");
  });

  it("selects the monitored site profile from the current page URL", () => {
    expect(monitoredSiteForUrl(policy, "https://public-ai-4.example.invalid/chat")?.site_id).toBe("public_ai_4");
    expect(monitoredSiteForUrl(policy, "https://outside.example.invalid/chat")).toBeUndefined();
  });
});
