import type { MonitoredSite } from "@prompt-egress-guard/core/browser";

export interface PromptCandidate {
  element: HTMLElement | HTMLInputElement | HTMLTextAreaElement;
  text: string;
  selector: string;
  warnings: string[];
}

export function isPromptInputElement(element: Element): element is HTMLElement | HTMLInputElement | HTMLTextAreaElement {
  if (!(element instanceof HTMLElement)) return false;
  if (element.dataset.pegIgnore === "true") return false;
  if (element instanceof HTMLInputElement) {
    const type = (element.getAttribute("type") ?? "text").toLowerCase();
    if (["password", "file", "hidden", "checkbox", "radio", "submit", "button"].includes(type)) return false;
    const autocomplete = (element.getAttribute("autocomplete") ?? "").toLowerCase();
    if (autocomplete.includes("cc-") || autocomplete.includes("password")) return false;
    return ["text", "search", ""].includes(type);
  }
  if (element instanceof HTMLTextAreaElement) return !element.hidden;
  if (element.isContentEditable || element.getAttribute("contenteditable") === "true") return true;
  if (element.getAttribute("role") === "textbox") return true;
  return false;
}

export function elementText(element: HTMLElement | HTMLInputElement | HTMLTextAreaElement): string {
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) return element.value;
  return element.innerText || element.textContent || "";
}

export function findPromptCandidates(documentRef: Document, site: MonitoredSite): PromptCandidate[] {
  const candidates: PromptCandidate[] = [];
  for (const selector of site.prompt_selectors) {
    let elements: Element[] = [];
    try {
      elements = Array.from(documentRef.querySelectorAll(selector));
    } catch {
      continue;
    }
    for (const element of elements) {
      if (!isPromptInputElement(element)) continue;
      const typed = element as HTMLElement | HTMLInputElement | HTMLTextAreaElement;
      const text = elementText(typed);
      if (!text.trim()) continue;
      candidates.push({ element: typed, text, selector, warnings: [] });
    }
  }
  return candidates;
}

export function choosePromptCandidate(candidates: PromptCandidate[], activeElement?: Element | null, submitTarget?: Element | null): PromptCandidate | undefined {
  if (candidates.length === 0) return undefined;
  const active = candidates.find((candidate) => candidate.element === activeElement);
  if (active) return active;
  if (submitTarget) {
    const form = closestForm(submitTarget);
    const inForm = form ? candidates.find((candidate) => closestForm(candidate.element) === form) : undefined;
    if (inForm) return inForm;
  }
  return [...candidates].sort((a, b) => b.text.trim().length - a.text.trim().length)[0];
}

export function capturePrompt(documentRef: Document, site: MonitoredSite, activeElement?: Element | null, submitTarget?: Element | null): { prompt: string; warnings: string[]; candidate?: PromptCandidate } {
  const candidates = findPromptCandidates(documentRef, site);
  if (candidates.length === 0) return { prompt: "", warnings: ["PROMPT_INPUT_NOT_FOUND"] };
  const warnings = candidates.length > 1 ? ["MULTIPLE_PROMPT_INPUTS_FOUND"] : [];
  const candidate = choosePromptCandidate(candidates, activeElement, submitTarget);
  return { prompt: candidate?.text ?? "", warnings, candidate };
}

function closestForm(element: Element): HTMLFormElement | null {
  return element instanceof HTMLElement ? element.closest("form") : null;
}
