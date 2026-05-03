import fs from "node:fs";
import yaml from "js-yaml";
import { describe, expect, it } from "vitest";
import {
  detectSecrets,
  detectSourceCode,
  detectCustomerRecords,
  detectHealthData,
  detectLegalText,
  detectInternalIdentifiers,
  detectPersonalData,
  detectFinancialData,
  PolicySchema,
  scanPrompt,
  validatePolicy
} from "@prompt-egress-guard/core";

const defaultPolicy = PolicySchema.parse(yaml.load(fs.readFileSync("examples/policies/default-policy.yml", "utf8")));

describe("policy validation", () => {
  it("parses a valid policy with five monitored example sites", () => {
    const result = validatePolicy(yaml.load(fs.readFileSync("examples/policies/default-policy.yml", "utf8")));
    expect(result.valid).toBe(true);
    expect(result.policy?.monitored_sites).toHaveLength(5);
  });

  it("fails invalid thresholds", () => {
    const policy = structuredClone(defaultPolicy);
    policy.actions.thresholds.block_score = 10;
    const result = validatePolicy(policy);
    expect(result.valid).toBe(false);
    expect(result.blockers).toContain("THRESHOLDS_INVALID");
  });

  it("example policy uses only example.invalid monitored domains", () => {
    const text = fs.readFileSync("examples/policies/default-policy.yml", "utf8");
    const hosts = [...text.matchAll(/https:\/\/([^/"]+)\/\*/g)].map((match) => match[1]);
    expect(hosts).toHaveLength(5);
    expect(hosts.every((host) => host.endsWith(".example.invalid"))).toBe(true);
  });

  it("fails unsafe include_prompt without acknowledgement", () => {
    const policy = structuredClone(defaultPolicy);
    policy.approved_destination!.include_prompt = true;
    policy.approved_destination!.unsafe_prompt_transfer_acknowledgement = false;
    expect(validatePolicy(policy).blockers).toContain("UNSAFE_PROMPT_TRANSFER_WITHOUT_ACK");
  });

  it("fails unsafe raw prompt storage without acknowledgement", () => {
    const policy = structuredClone(defaultPolicy);
    policy.audit.store_raw_prompt = true;
    policy.audit.unsafe_audit_storage_acknowledgement = false;
    expect(validatePolicy(policy).blockers).toContain("RAW_PROMPT_STORAGE_WITHOUT_ACK");
  });

  it("fails broad host permissions without acknowledgement", () => {
    const policy = structuredClone(defaultPolicy);
    policy.monitored_sites[0].host_permissions = ["<all_urls>"];
    expect(validatePolicy(policy).blockers).toContain("UNSAFE_BROAD_HOST_PERMISSIONS_WITHOUT_ACK");
  });
});

describe("deterministic detectors", () => {
  it("finds private key blocks", () => {
    const result = detectSecrets("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----", defaultPolicy.scanner);
    expect(result.reason_codes).toContain("PRIVATE_KEY_BLOCK_DETECTED");
  });

  it("finds bearer tokens", () => {
    const result = detectSecrets("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789", defaultPolicy.scanner);
    expect(result.reason_codes).toContain("BEARER_TOKEN_DETECTED");
  });

  it("finds connection string passwords", () => {
    const result = detectSecrets("database connection password=s3cretValue", defaultPolicy.scanner);
    expect(result.reason_codes).toContain("CONNECTION_STRING_SECRET_DETECTED");
  });

  it("finds high-entropy secret candidates near labels", () => {
    const result = scanPrompt(defaultPolicy, "secret token value AbCdEfGhIjKlMnOpQrStUvWxYz1234567890");
    expect(result.reason_codes).toContain("HIGH_ENTROPY_SECRET_CANDIDATE");
  });

  it("finds code blocks, stack traces, and SQL code", () => {
    expect(detectSourceCode("```ts\nfunction x() { return 1 }\n```").reason_codes).toContain("CODE_BLOCK_DETECTED");
    expect(detectSourceCode('Traceback (most recent call last):\nFile "x.py", line 3').reason_codes).toContain("STACK_TRACE_DETECTED");
    expect(detectSourceCode("CREATE TABLE records (id int);").reason_codes).toContain("SQL_CODE_PATTERN_DETECTED");
  });

  it("customer records require combination evidence", () => {
    expect(detectCustomerRecords("Taylor Example").matches).toHaveLength(0);
    expect(detectCustomerRecords("customer_id: C-1000 support ticket T-2000").reason_codes).toContain("CUSTOMER_RECORD_PATTERN_DETECTED");
  });

  it("finds health, legal, internal, personal, and financial indicators", () => {
    expect(detectHealthData("patient_id: PT-1234 diagnosis: cough medication: test dose").reason_codes).toContain("PATIENT_IDENTIFIER_PATTERN_DETECTED");
    expect(detectLegalText("privileged and confidential matter number MAT-1234").reason_codes).toContain("LEGAL_PRIVILEGE_PATTERN_DETECTED");
    expect(detectInternalIdentifiers("prod db01.internal 10.0.0.4 INC-1001").reason_codes).toContain("PRIVATE_IP_PATTERN_DETECTED");
    expect(detectPersonalData("Name: Taylor Example email taylor@example.invalid phone +1 555 010 2222").reason_codes).toContain("EMAIL_ADDRESS_DETECTED");
    expect(detectFinancialData("card 4111 1111 1111 1111 payroll").reason_codes).toContain("PAYMENT_CARD_CANDIDATE_DETECTED");
  });
});
