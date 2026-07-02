"""HTTP routes for engagements. Thin: parse, authorize, delegate, map."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.repository import AssetRepository
from app.modules.authorizations.repository import AuthorizationRepository
from app.modules.engagements.repository import EngagementRepository
from app.modules.engagements.schemas import (
    EngagementCreate,
    EngagementResponse,
    EngagementUpdate,
    KillSwitchRequest,
)
from app.modules.engagements.service import EngagementService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.platform.clock import Clock, get_clock
from app.platform.dependencies import get_session

router = APIRouter(tags=["engagements"])


def _service(
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> EngagementService:
    return EngagementService(
        EngagementRepository(session),
        AuthorizationRepository(session),
        AssetRepository(session),
        ProjectRepository(session),
        OrganizationRepository(session),
        clock,
    )


@router.post(
    "/api/v1/projects/{project_id}/engagements",
    status_code=status.HTTP_201_CREATED,
)
async def create_engagement(
    project_id: UUID,
    payload: EngagementCreate,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.create(tenant, project_id, payload)
    return EngagementResponse.model_validate(engagement)


@router.get("/api/v1/projects/{project_id}/engagements")
async def list_engagements(
    project_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> list[EngagementResponse]:
    engagements = await service.list_for_project(project_id, tenant)
    return [EngagementResponse.model_validate(eng) for eng in engagements]


@router.get("/api/v1/engagements/{engagement_id}")
async def get_engagement(
    engagement_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.get_for_tenant(engagement_id, tenant)
    return EngagementResponse.model_validate(engagement)


@router.patch("/api/v1/engagements/{engagement_id}")
async def update_engagement(
    engagement_id: UUID,
    payload: EngagementUpdate,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.update(engagement_id, tenant, payload)
    return EngagementResponse.model_validate(engagement)


@router.post("/api/v1/engagements/{engagement_id}/schedule")
async def schedule_engagement(
    engagement_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.schedule(engagement_id, tenant)
    return EngagementResponse.model_validate(engagement)


@router.post("/api/v1/engagements/{engagement_id}/activate")
async def activate_engagement(
    engagement_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.activate(engagement_id, tenant)
    return EngagementResponse.model_validate(engagement)


@router.post("/api/v1/engagements/{engagement_id}/pause")
async def pause_engagement(
    engagement_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.pause(engagement_id, tenant)
    return EngagementResponse.model_validate(engagement)


@router.post("/api/v1/engagements/{engagement_id}/resume")
async def resume_engagement(
    engagement_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.resume(engagement_id, tenant)
    return EngagementResponse.model_validate(engagement)


@router.post("/api/v1/engagements/{engagement_id}/complete")
async def complete_engagement(
    engagement_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.complete(engagement_id, tenant)
    return EngagementResponse.model_validate(engagement)


@router.post("/api/v1/engagements/{engagement_id}/cancel")
async def cancel_engagement(
    engagement_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.cancel(engagement_id, tenant)
    return EngagementResponse.model_validate(engagement)


@router.post("/api/v1/engagements/{engagement_id}/kill-switch")
async def set_kill_switch(
    engagement_id: UUID,
    payload: KillSwitchRequest,
    tenant: TenantContext = Depends(require_tenant_context),
    service: EngagementService = Depends(_service),
) -> EngagementResponse:
    engagement = await service.set_kill_switch(engagement_id, tenant, payload)
    return EngagementResponse.model_validate(engagement)
