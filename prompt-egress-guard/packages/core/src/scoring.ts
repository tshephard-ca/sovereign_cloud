import type { Action, CategoryResult, Confidence, DetectorCategory, Policy } from "./models.js";

const actionRank: Record<Action, number> = { ALLOW: 0, WARN: 1, REDIRECT: 2, BLOCK: 3 };
const orderedActions: Action[] = ["ALLOW", "WARN", "REDIRECT", "BLOCK"];

export function combineScores(results: CategoryResult[]): number {
  return Math.min(100, results.reduce((sum, result) => sum + result.risk_score, 0));
}

export function aggregateConfidence(results: CategoryResult[]): Confidence {
  if (results.some((result) => result.confidence === "HIGH")) return "HIGH";
  const mediumCount = results.filter((result) => result.confidence === "MEDIUM").length;
  if (mediumCount >= 1 || results.length >= 2) return "MEDIUM";
  return results.length ? "LOW" : "LOW";
}

export function actionFromThresholds(score: number, policy: Policy): Action {
  const thresholds = policy.actions.thresholds;
  if (score >= thresholds.block_score) return "BLOCK";
  if (score >= thresholds.redirect_score) return "REDIRECT";
  if (score >= thresholds.warn_score) return "WARN";
  return policy.actions.default_action;
}

export function categoryAction(category: DetectorCategory, policy: Policy): Action {
  return policy.actions.category_actions[category];
}

export function strongestAction(actions: Action[]): Action {
  return actions.reduce((strongest, action) => (actionRank[action] > actionRank[strongest] ? action : strongest), "ALLOW" as Action);
}

export function applyPolicyMode(action: Action, policy: Policy): Action {
  if (policy.mode === "observe") return "ALLOW";
  if (policy.mode === "warn" && actionRank[action] > actionRank.WARN) return "WARN";
  return action;
}

export function decideAction(score: number, results: CategoryResult[], policy: Policy): Action {
  const thresholdAction = actionFromThresholds(score, policy);
  const categoryActions = results.map((result) => categoryAction(result.category, policy));
  return applyPolicyMode(strongestAction([thresholdAction, ...categoryActions]), policy);
}

export function actionReason(action: Action): string {
  return `ACTION_${action}`;
}

export function actionByRank(rank: number): Action {
  return orderedActions[Math.max(0, Math.min(rank, orderedActions.length - 1))];
}
