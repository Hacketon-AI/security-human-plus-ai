"""FastAPI Router for AI Proof-of-Risk.

Exposes the AI Proof-of-Risk analysis endpoint safely.
"""

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

router = APIRouter(prefix="/ai-proof-of-risk", tags=["ai-proof-of-risk"])


def get_evidence_provider() -> ExecutionEvidenceProvider:
    """Dependency injection for the evidence provider."""
    # Step 3 uses Fake provider by default to maintain safe isolation
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
    provider: ExecutionEvidenceProvider = Depends(get_evidence_provider),
    config: ServiceConfig = Depends(get_service_config),
) -> Any:
    """Analyze a validation execution using the AI Proof-of-Risk Engine."""

    service = AIProofOfRiskService(evidence_provider=provider, config=config)

    try:
        response = service.analyze_execution(execution_id=execution_id, request=request)
        return response
    except MissingExecutionError as e:
        # Uniform 404 for missing or cross-tenant executions
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found.",
        ) from e
    except UnverifiedAssetError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal analysis error.",
        ) from e
