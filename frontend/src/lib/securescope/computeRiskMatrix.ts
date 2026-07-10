import type { ValidationExecution } from "./types";

/**
 * Cross-tabulates ValidationExecution objects by riskTier and outcome.
 * Returns a nested Record where each cell holds the count of matching executions.
 * Missing cells are omitted (zero-fill at render time).
 */
export function computeRiskMatrix(
  executions: ValidationExecution[]
): Record<string, Record<string, number>> {
  return executions.reduce((acc, e) => {
    const tier = e.riskTier;
    const outcome = e.outcome ?? "inconclusive";
    acc[tier] ??= {};
    acc[tier][outcome] = (acc[tier][outcome] ?? 0) + 1;
    return acc;
  }, {} as Record<string, Record<string, number>>);
}
