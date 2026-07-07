"""Report Generator.

Generates comprehensive summaries for the AI Proof-of-Risk analysis.
"""

from typing import Any

from app.modules.ai_proof_of_risk.enums import Audience
from app.modules.ai_proof_of_risk.schemas import (
    DigitalTwinScenario,
    ProofOfRiskArtifact,
    RemediationPlan,
    RetestPlan,
    RiskTribunalVerdict,
)


def generate_report(
    audience: Audience,
    attack_surface_graph: dict[str, Any] | None,
    exploitability_hypotheses: list[str] | None,
    scenarios: list[DigitalTwinScenario] | None,
    sandbox_proofs: list[ProofOfRiskArtifact] | None,
    tribunal_verdict: RiskTribunalVerdict | None,
    remediation_plan: RemediationPlan | None,
    retest_plan: RetestPlan | None,
) -> dict[str, Any]:
    """Generates the executive and technical summaries along with limitations."""

    # Mandatory safety statement
    safety_statement = (
        "Real exploit validation was performed only inside a controlled SecureScope "
        "digital twin sandbox. The production/authorized domain received safe, "
        "non-destructive validation only."
    )

    executive_summary = (
        f"AI Proof-of-Risk Analysis for audience {audience.value}. "
        "The analysis evaluated missing controls and generated simulated "
        "attack scenarios."
    )

    technical_summary = (
        "Technical analysis identified potential exploit vectors based on "
        "the attack surface graph."
    )

    if sandbox_proofs:
        executive_summary += (
            f" Sandbox simulation confirmed {len(sandbox_proofs)} vulnerabilities."
        )
        technical_summary += (
            f" Executed {len(sandbox_proofs)} deterministic simulation handlers."
        )

    return {
        "executive_summary": executive_summary,
        "technical_summary": technical_summary,
        "limitations": ["Deterministic mock data", "No real LLM reasoning performed"],
        "safety_statement": safety_statement,
    }
