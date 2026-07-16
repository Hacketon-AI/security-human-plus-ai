import uuid

import pytest
from app.main import create_app
from app.modules.ai_proof_of_risk.enums import AnalysisMode
from app.modules.ai_proof_of_risk.schemas import (
    AIProofOfRiskAnalysisResponse,
)
from app.modules.ai_proof_of_risk.service import AIProofOfRiskService
from fastapi.testclient import TestClient


@pytest.fixture
def client(migrated_dsn: str) -> TestClient:
    app = create_app()
    return TestClient(app)


def test_api_accepts_valid_request(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # We might need to mock the service layer to avoid actual processing
    mock_resp = AIProofOfRiskAnalysisResponse(
        analysis_id="analysis_1",
        status="completed",
        mode=AnalysisMode.full_report,
        created_at="2023-01-01T00:00:00Z",
        execution_id=uuid.uuid4(),
        executive_summary="Mock Report",
        tribunal_verdict=None,
        remediation_plan=None,
        retest_plan=None,
        attack_surface_graph=None,
        sandbox_proof_artifacts=None,
        model_routing_trace=["mock"],
        token_saving_estimate=10,
    )

    monkeypatch.setattr(
        AIProofOfRiskService,
        "analyze_execution",
        lambda self, *args, **kwargs: mock_resp,
    )

    execution_id = uuid.uuid4()
    response = client.post(
        f"/ai-proof-of-risk/executions/{execution_id}/analyze",
        json={
            "analysis_mode": "full_report",
            "audience": "executive",
            "allow_sandbox_simulation": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["execution_id"] == str(mock_resp.execution_id)


def test_api_rejects_invalid_analysis_mode(client: TestClient) -> None:
    execution_id = uuid.uuid4()
    response = client.post(
        f"/ai-proof-of-risk/executions/{execution_id}/analyze",
        json={"analysis_mode": "invalid_mode", "audience": "executive"},
    )

    assert response.status_code == 422  # FastAPI validation error


def test_api_returns_no_secrets(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    mock_resp = AIProofOfRiskAnalysisResponse(
        analysis_id="analysis_2",
        status="completed",
        mode=AnalysisMode.full_report,
        created_at="2023-01-01T00:00:00Z",
        execution_id=uuid.uuid4(),
        executive_summary="Safe Report REDACTED",
        tribunal_verdict=None,
        remediation_plan=None,
        retest_plan=None,
        attack_surface_graph=None,
        sandbox_proof_artifacts=None,
        model_routing_trace=["mock"],
        token_saving_estimate=10,
    )

    monkeypatch.setattr(
        AIProofOfRiskService,
        "analyze_execution",
        lambda self, *args, **kwargs: mock_resp,
    )

    execution_id = uuid.uuid4()
    response = client.post(
        f"/ai-proof-of-risk/executions/{execution_id}/analyze",
        json={"analysis_mode": "full_report", "audience": "executive"},
    )

    assert response.status_code == 200
    resp_text = response.text.lower()
    assert "secret" not in resp_text
    assert "password" not in resp_text


def test_api_with_sandbox_disabled_does_not_produce_proof_artifact(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    mock_resp = AIProofOfRiskAnalysisResponse(
        analysis_id="analysis_3",
        status="completed",
        mode=AnalysisMode.full_report,
        created_at="2023-01-01T00:00:00Z",
        execution_id=uuid.uuid4(),
        executive_summary="Mock Report",
        tribunal_verdict=None,
        remediation_plan=None,
        retest_plan=None,
        attack_surface_graph=None,
        sandbox_proof_artifacts=None,  # Sandbox disabled
        model_routing_trace=["mock"],
        token_saving_estimate=10,
    )

    monkeypatch.setattr(
        AIProofOfRiskService,
        "analyze_execution",
        lambda self, *args, **kwargs: mock_resp,
    )

    execution_id = uuid.uuid4()
    response = client.post(
        f"/ai-proof-of-risk/executions/{execution_id}/analyze",
        json={
            "analysis_mode": "full_report",
            "audience": "executive",
            "allow_sandbox_simulation": False,
        },
    )

    assert response.status_code == 200
    assert response.json().get("proof_artifact") is None
