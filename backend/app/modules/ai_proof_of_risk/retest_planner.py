"""Retest Planner.

Deterministic retest plan generation for digital twin scenarios.
"""

from app.modules.ai_proof_of_risk.schemas import DigitalTwinScenario, RetestPlan


def generate_retest_plan(scenario: DigitalTwinScenario) -> RetestPlan:
    """Generates a safe retest plan without executing worker logic."""

    return RetestPlan(
        retest_checklist=["Deploy fix", "Trigger scan", "Verify output"],
        before_state="Vulnerable to " + scenario.vulnerability_pattern,
        expected_after_state="Secure configuration enforced.",
        safe_validation_template="Run validation worker against staging.",
        success_criteria=["Finding no longer present in validation results."],
        evidence_needed=["Updated HTTP headers or configuration."],
        risk_delta_if_fixed="Risk eliminated for this vector.",
    )
