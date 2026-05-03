import type { CategoryResult, DetectorMatch } from "../models.js";
import { matchAll, result } from "./utils.js";

export function detectSourceCode(text: string): CategoryResult {
  const matches: DetectorMatch[] = [];
  const reasons: string[] = [];
  collect(matches, reasons, matchAll(text, /```(?:[a-z0-9_+-]+)?\n[\s\S]+?```/gi, "code_fence", "<CODE_REDACTED>"), "CODE_BLOCK_DETECTED");
  collect(matches, reasons, matchAll(text, /\b(?:function\s+[A-Za-z_$][\w$]*\s*\(|def\s+[A-Za-z_]\w*\s*\(|class\s+[A-Za-z_]\w*|public\s+class\s+\w+|func\s+\w+\s*\()/g, "code_declaration", "function <REDACTED>(...)"), "SOURCE_CODE_PATTERN_DETECTED");
  collect(matches, reasons, matchAll(text, /^\s*(?:import|require|include|from\s+\S+\s+import)\s+.+$/gim, "code_import", "import <REDACTED>"), "SOURCE_CODE_PATTERN_DETECTED");
  collect(matches, reasons, matchAll(text, /\b(?:Traceback \(most recent call last\)|Exception in thread|at\s+[\w.$]+\([^)]*:\d+\)|File ".+?", line \d+)/g, "code_stack_trace", "<STACK_TRACE_REDACTED>"), "STACK_TRACE_DETECTED");
  collect(matches, reasons, matchAll(text, /\b(?:CREATE\s+TABLE|CREATE\s+PROCEDURE|SELECT\s+.+\s+FROM|ALTER\s+TABLE|INSERT\s+INTO)\b/gi, "code_sql", "<SQL_REDACTED>"), "SQL_CODE_PATTERN_DETECTED");
  collect(matches, reasons, matchAll(text, /\b(?:package\.json|pyproject\.toml|Cargo\.toml|go\.mod|src\/|lib\/|internal\/|TODO|FIXME|BUG-\d{2,})\b/gi, "code_repository_context", "<REPOSITORY_CONTEXT_REDACTED>"), "REPOSITORY_CONTEXT_DETECTED");
  const longIndented = /(?:^ {4,}\S.*\n){3,}/m.exec(text);
  if (longIndented?.index !== undefined) {
    matches.push({ rule_id: "code_indentation_block", start: longIndented.index, end: longIndented.index + longIndented[0].length, redacted: "<CODE_REDACTED>" });
    reasons.push("SOURCE_CODE_PATTERN_DETECTED");
  }
  return result("source_code", reasons.includes("STACK_TRACE_DETECTED") || reasons.includes("CODE_BLOCK_DETECTED") ? 45 : 35, reasons.length > 1 ? "MEDIUM" : "LOW", matches, reasons);
}

function collect(matches: DetectorMatch[], reasons: string[], found: DetectorMatch[], reason: string): void {
  if (found.length) {
    matches.push(...found);
    reasons.push(reason);
  }
}
