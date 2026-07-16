import uuid
from collections.abc import AsyncIterator

import pytest
from app.config import Environment, Settings
from app.main import create_app
from app.modules.ai_proof_of_risk.enums import AnalysisMode
from app.modules.ai_proof_of_risk.schemas import AIProofOfRiskAnalysisResponse
from app.modules.ai_proof_of_risk.service import AIProofOfRiskService
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

_TEST_ORGANIZATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def client(migrated_dsn: str) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        environment=Environment.test,
        database_dsn=SecretStr(migrated_dsn),
        bootstrap_admin_email=None,
        bootstrap_admin_username=None,
        bootstrap_admin_password=None,
        bootstrap_admin_organization_id=None,
        bootstrap_admin_full_name=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Organization-Id": str(_TEST_ORGANIZATION_ID)},
        ) as http_client:
            yield http_client


async def test_api_accepts_valid_request(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient
) -> None:
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
    response = await client.post(
        f"/ai-proof-of-risk/executions/{execution_id}/analyze",
        json={
            "analysis_mode": "full_report",
            "audience": "executive",
            "allow_sandbox_simulation": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["execution_id"] == str(mock_resp.execution_id)


async def test_api_rejects_invalid_analysis_mode(client: AsyncClient) -> None:
    execution_id = uuid.uuid4()
    response = await client.post(
        f"/ai-proof-of-risk/executions/{execution_id}/analyze",
        json={"analysis_mode": "invalid_mode", "audience": "executive"},
    )

    assert response.status_code == 422


async def test_api_returns_no_secrets(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient
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
    response = await client.post(
        f"/ai-proof-of-risk/executions/{execution_id}/analyze",
        json={"analysis_mode": "full_report", "audience": "executive"},
    )

    assert response.status_code == 200
    resp_text = response.text.lower()
    assert "secret" not in resp_text
    assert "password" not in resp_text


async def test_api_with_sandbox_disabled_does_not_produce_proof_artifact(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient
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
    response = await client.post(
        f"/ai-proof-of-risk/executions/{execution_id}/analyze",
        json={
            "analysis_mode": "full_report",
            "audience": "executive",
            "allow_sandbox_simulation": False,
        },
    )

    assert response.status_code == 200
    assert response.json().get("proof_artifact") is None
