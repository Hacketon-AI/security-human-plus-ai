"""HTTP routes for assets. Thin: parse, authorize, delegate, map."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.repository import AssetRepository
from app.modules.assets.schemas import (
    AssetCreate,
    AssetResponse,
    AssetUpdate,
    AssetVerificationRequest,
)
from app.modules.assets.service import AssetService
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.platform.clock import Clock, get_clock
from app.platform.dependencies import get_session

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


def _service(
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> AssetService:
    return AssetService(
        AssetRepository(session),
        ProjectRepository(session),
        clock,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_asset(
    payload: AssetCreate,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetService = Depends(_service),
) -> AssetResponse:
    asset = await service.register(tenant, payload)
    return AssetResponse.model_validate(asset)


@router.get("")
async def list_assets(
    project_id: UUID | None = None,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetService = Depends(_service),
) -> list[AssetResponse]:
    assets = await service.list_for_tenant(tenant, project_id)
    return [AssetResponse.model_validate(asset) for asset in assets]


@router.get("/{asset_id}")
async def get_asset(
    asset_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetService = Depends(_service),
) -> AssetResponse:
    asset = await service.get_for_tenant(asset_id, tenant)
    return AssetResponse.model_validate(asset)


@router.patch("/{asset_id}")
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetService = Depends(_service),
) -> AssetResponse:
    asset = await service.update(asset_id, tenant, payload)
    return AssetResponse.model_validate(asset)


@router.post("/{asset_id}/request-verification")
async def request_asset_verification(
    asset_id: UUID,
    payload: AssetVerificationRequest,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetService = Depends(_service),
) -> AssetResponse:
    asset = await service.request_verification(asset_id, tenant, payload)
    return AssetResponse.model_validate(asset)
