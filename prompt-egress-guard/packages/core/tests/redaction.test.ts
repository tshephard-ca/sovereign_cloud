import { describe, expect, it } from "vitest";
import { promptHash, redactText } from "@prompt-egress-guard/core";

describe("redaction", () => {
  it("removes secrets, emails, and payment cards", () => {
    const redacted = redactText("api_key=abcdefghijklmnopqrstuvwx email taylor@example.invalid card 4111 1111 1111 1111", 500);
    expect(redacted).toContain("<SECRET_REDACTED>");
    expect(redacted).toContain("<EMAIL_REDACTED>");
    expect(redacted).toContain("<PAYMENT_CARD_REDACTED>");
  });

  it("returns stable truncated prompt hashes", () => {
    expect(promptHash("same prompt")).toBe(promptHash("same prompt"));
    expect(promptHash("same prompt")).toHaveLength(16);
  });
});
