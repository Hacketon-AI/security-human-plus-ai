// Feature: frontend-audit, Property 1: RiskDistributionMatrix partition invariant
// Validates: Requirements 1.3, 1.4

import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { computeRiskMatrix } from "../computeRiskMatrix";
import type { ValidationExecution, RiskTier, ExecutionOutcome } from "../types";

// ─── Arbitraries ──────────────────────────────────────────────────────────────

const riskTierArb: fc.Arbitrary<RiskTier> = fc.constantFrom(
  "low",
  "moderate",
  "high",
  "critical"
);

const outcomeArb: fc.Arbitrary<ExecutionOutcome | null> = fc.oneof(
  fc.constantFrom<ExecutionOutcome>(
    "validated",
    "failed_safely",
    "blocked_by_control",
    "inconclusive",
    "not_reproduced"
  ),
  fc.constant(null)
);

/** Minimal ValidationExecution with only the fields computeRiskMatrix reads */
const executionArb: fc.Arbitrary<Pick<ValidationExecution, "id" | "riskTier" | "outcome">> =
  fc.record({
    id: fc.uuid(),
    riskTier: riskTierArb,
    outcome: outcomeArb,
  });

const executionArrayArb = fc.array(executionArb, { maxLength: 200 });

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("computeRiskMatrix – Property 1: partition invariant", () => {
  /**
   * **Validates: Requirements 1.3, 1.4**
   *
   * Property 1a — cell-sum invariant:
   * The sum of all cell counts in the matrix must equal executions.length.
   */
  it("cell sum equals input length for any execution array", () => {
    fc.assert(
      fc.property(executionArrayArb, (executions) => {
        const matrix = computeRiskMatrix(
          executions as unknown as ValidationExecution[]
        );

        const cellSum = Object.values(matrix).flatMap(Object.values).reduce(
          (total, count) => total + count,
          0
        );

        expect(cellSum).toBe(executions.length);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 1.3, 1.4**
   *
   * Property 1b — no-duplicate-assignment invariant:
   * Each execution contributes exactly 1 to the total, meaning it appears in
   * at most one cell (partition invariant). Verified by asserting each cell
   * count is non-negative and the sum accounts for every element exactly once.
   */
  it("no execution appears in more than one cell", () => {
    fc.assert(
      fc.property(executionArrayArb, (executions) => {
        const matrix = computeRiskMatrix(
          executions as unknown as ValidationExecution[]
        );

        // Every cell count must be a positive integer (no phantom entries)
        for (const tierCounts of Object.values(matrix)) {
          for (const count of Object.values(tierCounts)) {
            expect(count).toBeGreaterThan(0);
            expect(Number.isInteger(count)).toBe(true);
          }
        }

        // Each id should map to exactly one (tier, outcome) bucket.
        // We verify this by re-deriving the expected per-bucket counts manually
        // and comparing against the function output.
        const expected: Record<string, Record<string, number>> = {};
        for (const e of executions) {
          const tier = e.riskTier;
          const outcome = e.outcome ?? "inconclusive";
          expected[tier] ??= {};
          expected[tier][outcome] = (expected[tier][outcome] ?? 0) + 1;
        }

        expect(matrix).toEqual(expected);
      }),
      { numRuns: 100 }
    );
  });
});
