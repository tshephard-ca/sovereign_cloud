// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { capturePrompt, findPromptCandidates } from "@prompt-egress-guard/extension";

const site = {
  site_id: "public_ai_1",
  display_name: "Public AI Site 1",
  host_permissions: ["https://public-ai-1.example.invalid/*"],
  prompt_selectors: ["textarea", "[contenteditable='true']", "input"],
  submit_selectors: ["button[type='submit']"],
  keyboard_submit: { ctrl_enter: true, cmd_enter: true, plain_enter: false }
};

describe("DOM capture", () => {
  it("finds textarea and contenteditable prompt inputs", () => {
    document.body.innerHTML = '<textarea>hello</textarea><div contenteditable="true">editable prompt</div>';
    expect(findPromptCandidates(document, site)).toHaveLength(2);
  });

  it("ignores password and file inputs", () => {
    document.body.innerHTML = '<input type="password" value="secret"><input type="file"><input type="text" value="ok">';
    const candidates = findPromptCandidates(document, site);
    expect(candidates).toHaveLength(1);
    expect(candidates[0].text).toBe("ok");
  });

  it("warns when no prompt is found and allows default caller behavior", () => {
    document.body.innerHTML = "<div>No prompt</div>";
    expect(capturePrompt(document, site).warnings).toContain("PROMPT_INPUT_NOT_FOUND");
  });

  it("chooses active prompt before largest non-empty candidate", () => {
    document.body.innerHTML = "<textarea id='small'>small</textarea><textarea id='large'>large prompt content</textarea>";
    const small = document.getElementById("small") as HTMLTextAreaElement;
    small.focus();
    expect(capturePrompt(document, site, small).prompt).toBe("small");
  });
});
