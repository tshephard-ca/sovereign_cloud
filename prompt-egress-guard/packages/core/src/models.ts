import { z } from "zod";

export const ActionSchema = z.enum(["ALLOW", "WARN", "REDIRECT", "BLOCK"]);
export const ConfidenceSchema = z.enum(["LOW", "MEDIUM", "HIGH"]);
export const ModeSchema = z.enum(["observe", "warn", "enforce"]);
export const DetectedRiskLevelSchema = z.enum(["NONE", "LOW", "MEDIUM", "HIGH"]);

export type Action = z.infer<typeof ActionSchema>;
export type Confidence = z.infer<typeof ConfidenceSchema>;
export type PolicyMode = z.infer<typeof ModeSchema>;
export type DetectedRiskLevel = z.infer<typeof DetectedRiskLevelSchema>;

export const KeyboardSubmitSchema = z.object({
  ctrl_enter: z.boolean().default(false),
  cmd_enter: z.boolean().default(false),
  plain_enter: z.boolean().default(false)
});

export const MonitoredSiteSchema = z.object({
  site_id: z.string().min(1),
  display_name: z.string().min(1),
  host_permissions: z.array(z.string().min(1)).min(1),
  prompt_selectors: z.array(z.string().min(1)).min(1),
  submit_selectors: z.array(z.string().min(1)).default([]),
  keyboard_submit: KeyboardSubmitSchema.default({})
});

export const ApprovedDestinationSchema = z.object({
  mode: z.literal("open_url"),
  url: z.string().min(1),
  include_prompt: z.boolean().default(false),
  include_reason_codes: z.boolean().default(true),
  include_handoff_id: z.boolean().default(true),
  unsafe_prompt_transfer_acknowledgement: z.boolean().default(false),
  clipboard_copy_allowed: z.boolean().default(false)
});

export const ActionThresholdsSchema = z.object({
  warn_score: z.number().int().min(0).max(100),
  redirect_score: z.number().int().min(0).max(100),
  block_score: z.number().int().min(0).max(100)
});

export const CategoryActionSchema = z.object({
  secrets: ActionSchema.default("BLOCK"),
  source_code: ActionSchema.default("REDIRECT"),
  customer_records: ActionSchema.default("REDIRECT"),
  health_data: ActionSchema.default("BLOCK"),
  legal_text: ActionSchema.default("REDIRECT"),
  internal_identifiers: ActionSchema.default("WARN"),
  personal_data: ActionSchema.default("WARN"),
  financial_data: ActionSchema.default("BLOCK")
});

export const ActionsPolicySchema = z.object({
  default_action: ActionSchema.default("ALLOW"),
  thresholds: ActionThresholdsSchema,
  category_actions: CategoryActionSchema
});

export const AuditPolicySchema = z.object({
  enabled: z.boolean().default(true),
  store_raw_prompt: z.boolean().default(false),
  store_redacted_excerpt: z.boolean().default(true),
  max_redacted_excerpt_chars: z.number().int().min(0).max(1000).default(160),
  store_prompt_hash: z.boolean().default(true),
  store_site_id: z.boolean().default(true),
  retention_days: z.number().int().min(1).max(365).default(7),
  max_events: z.number().int().min(1).max(100000).default(500),
  unsafe_audit_storage_acknowledgement: z.boolean().default(false)
});

export const ScannerPolicySchema = z.object({
  max_prompt_chars: z.number().int().min(100).max(1000000).default(20000),
  entropy_threshold: z.number().min(1).max(8).default(4.2),
  min_secret_length: z.number().int().min(8).max(200).default(20),
  confidence_floor_for_block: ConfidenceSchema.default("MEDIUM")
});

export const UserExperiencePolicySchema = z.object({
  show_reason_codes: z.boolean().default(true),
  allow_continue_on_warn: z.boolean().default(true),
  allow_continue_on_redirect: z.boolean().default(false),
  allow_continue_on_block: z.boolean().default(false),
  overlay_title: z.string().default("Sensitive prompt risk detected")
});

export const PolicySchema = z.object({
  policy_id: z.string().min(1),
  policy_version: z.number().int().positive(),
  mode: ModeSchema.default("enforce"),
  monitored_sites: z.array(MonitoredSiteSchema).min(1),
  approved_destination: ApprovedDestinationSchema.optional(),
  actions: ActionsPolicySchema,
  audit: AuditPolicySchema.default({}),
  scanner: ScannerPolicySchema.default({}),
  user_experience: UserExperiencePolicySchema.default({}),
  unsafe_broad_host_permissions_acknowledgement: z.boolean().default(false),
  dnr: z
    .object({
      enabled: z.boolean().default(false),
      redirect_to_extension_warning: z.boolean().default(false)
    })
    .default({})
});

export type MonitoredSite = z.infer<typeof MonitoredSiteSchema>;
export type ApprovedDestination = z.infer<typeof ApprovedDestinationSchema>;
export type ActionThresholds = z.infer<typeof ActionThresholdsSchema>;
export type CategoryActions = z.infer<typeof CategoryActionSchema>;
export type AuditPolicy = z.infer<typeof AuditPolicySchema>;
export type ScannerPolicy = z.infer<typeof ScannerPolicySchema>;
export type Policy = z.infer<typeof PolicySchema>;

export type DetectorCategory =
  | "secrets"
  | "source_code"
  | "customer_records"
  | "health_data"
  | "legal_text"
  | "internal_identifiers"
  | "personal_data"
  | "financial_data";

export interface DetectorMatch {
  rule_id: string;
  start: number;
  end: number;
  redacted: string;
}

export interface CategoryResult {
  category: DetectorCategory;
  risk_score: number;
  confidence: Confidence;
  matches: DetectorMatch[];
  reason_codes: string[];
}

export interface ScanResult {
  policy_id: string;
  site_id: string;
  action: Action;
  risk_status: Action;
  detected_risk_level: DetectedRiskLevel;
  base_action_from_score: Action;
  strongest_category_action: Action;
  final_action: Action;
  policy_mode: PolicyMode;
  allowed_user_actions: string[];
  decision_summary: string;
  risk_score: number;
  confidence: Confidence;
  categories: DetectorCategory[];
  reason_codes: string[];
  redacted_excerpt: string;
  prompt_hash: string;
  warnings: string[];
  blockers: string[];
}

export interface AuditEvent {
  event_id: string;
  timestamp: string;
  policy_id: string;
  site_id?: string;
  action: Action;
  risk_score: number;
  confidence: Confidence;
  categories: DetectorCategory[];
  reason_codes: string[];
  prompt_hash?: string;
  redacted_excerpt?: string;
  handoff_id?: string;
  user_decision?: string;
  raw_prompt?: string;
}

export interface HandoffEvent {
  handoff_id: string;
  policy_id: string;
  action: Action;
  reason_codes: string[];
  url: string;
}

export interface ExtensionSiteConfig {
  policy_id: string;
  mode: PolicyMode;
  sites: MonitoredSite[];
  approved_destination?: ApprovedDestination;
}

export interface DnrRule {
  id: number;
  priority: number;
  action: { type: "block" | "redirect"; redirect?: { extensionPath: string } };
  condition: { urlFilter: string; resourceTypes: string[] };
}

export interface ValidationResult {
  valid: boolean;
  policy?: Policy;
  warnings: string[];
  blockers: string[];
}
