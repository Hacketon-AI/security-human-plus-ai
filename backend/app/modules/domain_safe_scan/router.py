"""Authenticated entry point for authorized domain safety analysis."""

from fastapi import APIRouter, Depends, HTTPException

from app.modules.domain_safe_scan.schemas import (
    DomainSafeScanRequest,
    DomainSafeScanResponse,
)
from app.modules.domain_safe_scan.services import DomainSafeScanService
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context

router = APIRouter(prefix="/domain-safe-scan", tags=["domain-safe-scan"])
service = DomainSafeScanService()


@router.post("/analyze", response_model=DomainSafeScanResponse)
async def analyze_domain(
    request: DomainSafeScanRequest,
    tenant: TenantContext = Depends(require_tenant_context),
) -> DomainSafeScanResponse:
    """Analyze an authorized domain as an authenticated tenant operation."""
    try:
        return await service.analyze(
            request, organization_id=tenant.organization_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="Domain analysis failed") from None
