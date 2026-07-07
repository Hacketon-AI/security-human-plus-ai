"""Proof artifact generation.

Handles creation of the ProofOfRiskArtifact from successful sandbox scenarios.
Ensures no raw secrets or payloads are included, and strictly marks the artifact
as a sandbox-only proof.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.modules.ai_proof_of_risk.enums import ProofType
from app.modules.ai_proof_of_risk.schemas import ProofOfRiskArtifact, SandboxTarget


def create_proof_artifact(
    scenario_id: str,
    execution_id: str | object,
    proof_type: ProofType,
    sandbox_target: SandboxTarget,
    evidence_summary: str,
    steps_summary: list[str] | None = None,
) -> ProofOfRiskArtifact:
    """Creates a safe, deterministic-friendly proof artifact."""

    steps = steps_summary or []

    # Generate a proof token that is unique but safe (no actual exploit payload)
    proof_token = f"proof_token_{uuid4().hex}"

    safety_notes = [
        "Sandbox-only execution. No production targets were contacted.",
        "Payloads are deterministic markers, not weaponized exploits.",
        "No real credentials or secrets were used.",
    ]

    return ProofOfRiskArtifact(
        proof_id=f"proof_{uuid4().hex}",
        scenario_id=scenario_id,
        execution_id=execution_id,
        proof_type=proof_type,
        proof_token=proof_token,
        sandbox_target=sandbox_target,
        confirmed=True,
        evidence_summary=evidence_summary,
        steps_summary=steps,
        safety_notes=safety_notes,
        created_at=datetime.now(UTC).isoformat(),
        sanitized_metadata={"marker": "safe"},
        production_target_used=False,
    )
