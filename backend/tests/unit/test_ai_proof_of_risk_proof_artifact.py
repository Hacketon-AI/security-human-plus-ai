from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from app.modules.ai_proof_of_risk.enums import ProofType
from app.modules.ai_proof_of_risk.schemas import ProofOfRiskArtifact, SandboxTarget
from pydantic import ValidationError


def create_target() -> SandboxTarget:
    return SandboxTarget(
        sandbox_base_url="http://sandbox-fake.sandbox.internal",
        scenario_id="scenario-123",
        execution_id=uuid4(),
        allowed_host="example.com",
        allowed_scheme="http",
        is_ephemeral=True,
        created_by_securescope=True,
    )


def create_valid_artifact_kwargs() -> dict[str, Any]:
    return {
        "proof_id": "proof_123",
        "scenario_id": "scenario-123",
        "execution_id": uuid4(),
        "proof_type": ProofType.csp_sandbox_marker_execution,
        "proof_token": "token_123",
        "sandbox_target": create_target(),
        "confirmed": True,
        "evidence_summary": "Summary",
        "safety_notes": ["Sandbox-only execution."],
        "created_at": datetime.now(UTC).isoformat(),
        "sanitized_metadata": {"safe": "true"},
    }


def test_proof_production_target_used_is_false() -> None:
    kwargs = create_valid_artifact_kwargs()
    proof = ProofOfRiskArtifact(**kwargs)
    assert proof.production_target_used is False


def test_proof_contains_sandbox_only_safety_note() -> None:
    kwargs = create_valid_artifact_kwargs()
    proof = ProofOfRiskArtifact(**kwargs)
    assert any("sandbox" in note.lower() for note in proof.safety_notes)


def test_proof_contains_no_raw_secret() -> None:
    kwargs = create_valid_artifact_kwargs()
    kwargs["raw_secret"] = "super-secret-123"
    with pytest.raises(ValidationError):
        ProofOfRiskArtifact(**kwargs)


def test_proof_contains_no_raw_exploit_payload() -> None:
    kwargs = create_valid_artifact_kwargs()
    kwargs["raw_exploit_payload"] = "<script>alert(1)</script>"
    with pytest.raises(ValidationError):
        ProofOfRiskArtifact(**kwargs)


def test_proof_id_is_present() -> None:
    kwargs = create_valid_artifact_kwargs()
    del kwargs["proof_id"]
    with pytest.raises(ValidationError):
        ProofOfRiskArtifact(**kwargs)


def test_proof_token_is_present() -> None:
    kwargs = create_valid_artifact_kwargs()
    del kwargs["proof_token"]
    with pytest.raises(ValidationError):
        ProofOfRiskArtifact(**kwargs)


def test_sanitized_metadata_is_safe() -> None:
    kwargs = create_valid_artifact_kwargs()
    kwargs["sanitized_metadata"] = {"request_id": "req-123"}
    proof = ProofOfRiskArtifact(**kwargs)
    assert proof.sanitized_metadata["request_id"] == "req-123"
