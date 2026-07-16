"""FastAPI router for AI Proof-of-Risk analysis."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.ai_proof_of_risk.errors import (
    MissingExecutionError,
    UnverifiedAssetError,
)
from app.modules.ai_proof_of_risk.execution_evidence_provider import (
    ExecutionEvidenceProvider,
    FakeExecutionEvidenceProvider,
)
from app.modules.ai_proof_of_risk.schemas import (
    AIProofOfRiskAnalysisRequest,
    AIProofOfRiskAnalysisResponse,
)
from app.modules.ai_proof_of_risk.service import AIProofOfRiskService, ServiceConfig
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context

router = APIRouter(prefix="/ai-proof-of-risk", tags=["ai-proof-of-risk"])


def get_evidence_provider() -> ExecutionEvidenceProvider:
    """Dependency injection for the evidence provider."""
    return FakeExecutionEvidenceProvider()


def get_service_config() -> ServiceConfig:
    """Dependency injection for service configuration."""
    return ServiceConfig()


@router.post(
    "/executions/{execution_id}/analyze",
    response_model=AIProofOfRiskAnalysisResponse,
    status_code=status.HTTP_200_OK,
)
def analyze_execution(
    execution_id: UUID,
    request: AIProofOfRiskAnalysisRequest,
    tenant: TenantContext = Depends(require_tenant_context),
    provider: ExecutionEvidenceProvider = Depends(get_evidence_provider),
    config: ServiceConfig = Depends(get_service_config),
) -> Any:
    """Analyze evidence only for the authenticated organization."""
    service = AIProofOfRiskService(evidence_provider=provider, config=config)
    try:
        return service.analyze_execution(
            execution_id=execution_id,
            request=request,
            context={"organization_id": str(tenant.organization_id)},
        )
    except MissingExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found.",
        ) from exc
    except UnverifiedAssetError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis error.",
        ) from exc
