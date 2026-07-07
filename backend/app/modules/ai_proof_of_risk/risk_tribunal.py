"""Risk Tribunal Module.

Deterministic placeholder for Step 3. Returns safe, predefined tribunal verdicts
based on
the digital twin scenario.
"""

from app.modules.ai_proof_of_risk.schemas import (
    DigitalTwinScenario,
    RiskTribunalVerdict,
)


def generate_risk_tribunal(scenario: DigitalTwinScenario) -> RiskTribunalVerdict:
    """Generates a deterministic risk tribunal verdict for the scenario."""

    return RiskTribunalVerdict(
        attacker_view=(
            "The attacker can exploit the missing configuration to target users "
            "in the browser context."
        ),
        defender_view=(
            "The lack of controls introduces uncertainty. Mitigation requires "
            "proper headers."
        ),
        lab_view=(
            "Sandbox proof confirms the vulnerability is present in the "
            "isolated environment."
        ),
        judge_verdict=(
            "Vulnerability confirmed with high confidence based on deterministic "
            "simulation."
        ),
        severity="Medium",
        confidence="High",
        false_positive_risk="Low",
        business_impact="Potential unauthorized actions by users if targeted.",
        recommended_priority="P2",
        limitations=["Deterministic evaluation only. No production exploit performed."],
    )
