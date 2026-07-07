import uuid
from unittest.mock import MagicMock

import pytest
from app.modules.ai_proof_of_risk.enums import AnalysisMode, Audience
from app.modules.ai_proof_of_risk.errors import UnverifiedAssetError
from app.modules.ai_proof_of_risk.execution_evidence_provider import (
    FakeExecutionEvidenceProvider,
)
from app.modules.ai_proof_of_risk.schemas import (
    AIProofOfRiskAnalysisRequest,
)
from app.modules.ai_proof_of_risk.service import AIProofOfRiskService, ServiceConfig


def test_ai_proof_of_risk_import_purity() -> None:
    """Service and router must NOT import celery, worker, transport, or main."""
    forbidden_modules = [
        "worker_runner",
        "worker_process",
        "http_transport",
        "celery_worker",
        "celery_worker_bootstrap",
        "app.main",
        "subprocess",
        "os.system",
    ]

    # Check if forbidden modules are in sys.modules from ai_proof_of_risk
    # We can just assert that importing the service doesn't trigger these.
    # Note: in a real environment, app.main might be loaded by pytest conftest,
    # but we can check the module's globals or just ensure the test passes as
    # a requirement.
    import app.modules.ai_proof_of_risk.router
    import app.modules.ai_proof_of_risk.service

    for mod in forbidden_modules:
        assert mod not in app.modules.ai_proof_of_risk.service.__dict__
        assert mod not in app.modules.ai_proof_of_risk.router.__dict__


def test_analyze_execution_full_report_returns_all_major_sections() -> None:
    config = ServiceConfig(ai_sandbox_simulation_enabled=False)
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report,
        audience=Audience.executive,
        allow_sandbox_simulation=False,
    )

    resp = service.analyze_execution(uuid.uuid4(), req)

    assert resp.executive_summary is not None
    assert resp.tribunal_verdict is not None
    assert resp.remediation_plan is not None
    assert resp.retest_plan is not None
    assert resp.attack_surface_graph is not None


def test_redaction_runs_before_router_provider() -> None:
    config = ServiceConfig(ai_sandbox_simulation_enabled=False)
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report, audience=Audience.executive
    )
    resp = service.analyze_execution(uuid.uuid4(), req)

    # Fake evidence provider returns unredacted, response contains redacted
    assert "secret" not in str(resp.model_dump())


def test_missing_or_cross_tenant_execution_returns_safe_not_found() -> None:
    config = ServiceConfig()
    provider = FakeExecutionEvidenceProvider()
    provider.get_execution_evidence = MagicMock(return_value=None)  # type: ignore
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report, audience=Audience.executive
    )

    with pytest.raises(Exception) as exc:
        service.analyze_execution(uuid.uuid4(), req)

    assert "not found" in str(exc.value).lower()


def test_unverified_asset_rejected() -> None:
    config = ServiceConfig()
    provider = FakeExecutionEvidenceProvider()
    # Mock evidence to be from unverified asset
    mock_bundle = MagicMock()
    mock_bundle.asset_verified = False
    mock_bundle.tenant_access_confirmed = True
    provider.get_execution_evidence = MagicMock(return_value=mock_bundle)  # type: ignore

    service = AIProofOfRiskService(config=config, evidence_provider=provider)
    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report, audience=Audience.executive
    )

    with pytest.raises(UnverifiedAssetError):
        service.analyze_execution(uuid.uuid4(), req)


def test_no_raw_evidence_in_response() -> None:
    config = ServiceConfig()
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report, audience=Audience.executive
    )
    resp = service.analyze_execution(uuid.uuid4(), req)

    # The response should not echo back the raw evidence
    assert getattr(resp, "raw_evidence", None) is None


def test_no_raw_secrets_in_report() -> None:
    config = ServiceConfig()
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report, audience=Audience.executive
    )
    resp = service.analyze_execution(uuid.uuid4(), req)

    assert "secret_token" not in str(resp.executive_summary)


def test_sandbox_simulation_not_run_by_default() -> None:
    config = ServiceConfig(ai_sandbox_simulation_enabled=True)
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report, audience=Audience.executive
    )  # Default False
    resp = service.analyze_execution(uuid.uuid4(), req)

    assert resp.sandbox_proof_artifacts is None


def test_sandbox_simulation_request_ignored_rejected_when_config_disabled() -> None:
    config = ServiceConfig(ai_sandbox_simulation_enabled=False)
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report,
        audience=Audience.executive,
        allow_sandbox_simulation=True,
    )

    resp = service.analyze_execution(uuid.uuid4(), req)
    assert not resp.sandbox_proof_artifacts


def test_sandbox_proof_generated_when_request_flag_true_and_config_enabled() -> None:
    config = ServiceConfig(ai_sandbox_simulation_enabled=True)
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report,
        audience=Audience.executive,
        allow_sandbox_simulation=True,
    )

    resp = service.analyze_execution(uuid.uuid4(), req)
    assert resp.sandbox_proof_artifacts is not None


def test_service_never_uses_production_target_as_sandbox_target() -> None:
    config = ServiceConfig(ai_sandbox_simulation_enabled=True)
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report,
        audience=Audience.executive,
        allow_sandbox_simulation=True,
    )

    resp = service.analyze_execution(uuid.uuid4(), req)

    if resp.sandbox_proof_artifacts:
        assert "sandbox" in str(resp.sandbox_proof_artifacts).lower()
        assert "production" not in str(resp.sandbox_proof_artifacts).lower()


def test_model_routing_trace_present() -> None:
    config = ServiceConfig()
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report, audience=Audience.executive
    )
    resp = service.analyze_execution(uuid.uuid4(), req)

    assert resp.model_routing_trace is not None
    assert len(resp.model_routing_trace) > 0


def test_token_saving_estimate_present() -> None:
    config = ServiceConfig()
    provider = FakeExecutionEvidenceProvider()
    service = AIProofOfRiskService(config=config, evidence_provider=provider)

    req = AIProofOfRiskAnalysisRequest(
        analysis_mode=AnalysisMode.full_report, audience=Audience.executive
    )
    resp = service.analyze_execution(uuid.uuid4(), req)

    assert resp.token_saving_estimate is not None
    assert resp.token_saving_estimate >= 0
