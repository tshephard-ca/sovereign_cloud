import type { Action, DetectorCategory } from "@prompt-egress-guard/core";

export type PromptElementType = "textarea" | "input_text" | "contenteditable" | "role_textbox" | "password_negative" | "file_negative" | "none_negative";
export type SubmitPath = "button_click" | "form_submit" | "ctrl_enter" | "cmd_enter" | "plain_enter_disabled" | "no_submit";

export interface PromptRecord {
  prompt_id: string;
  site_id: string;
  element_type: PromptElementType;
  submit_path: SubmitPath;
  business_workflow: string;
  expected_action: Action;
  expected_categories: DetectorCategory[];
  sensitivity_family: "none" | "secrets" | "source_code" | "customer_records" | "health_data" | "legal_text" | "internal_identifiers" | "personal_data" | "financial_data";
  synthetic: boolean;
  prompt: string;
  notes: string;
}

export interface GapFinding {
  area: "input" | "output";
  severity: "REVIEW";
  code: string;
  description: string;
  business_impact: string;
  suggested_fix: string;
}

export interface BusinessImpactFinding {
  code: string;
  action: Action;
  impact: string;
  question: string;
}

export interface PilotAssessment {
  status: "PASS" | "REVIEW";
  executive_summary: {
    protected_workflow_count: number;
    configured_site_count: number;
    risky_prompt_count: number;
    blocked_count: number;
    redirected_count: number;
    warned_count: number;
    allowed_count: number;
    core_message: string;
  };
  input_coverage: Record<string, unknown>;
  output_coverage: Record<string, unknown>;
  workflow_table: Array<{
    prompt_id: string;
    workflow: string;
    expected_action: Action;
    actual_action?: Action;
    categories: DetectorCategory[];
    business_meaning: string;
  }>;
  business_impact_findings: BusinessImpactFinding[];
  admin_questions: string[];
  input_gaps: GapFinding[];
  output_gaps: GapFinding[];
}
