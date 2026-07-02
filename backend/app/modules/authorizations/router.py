"""HTTP routes for authorizations. Thin: parse, authorize, delegate, map."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.repository import AssetRepository
from app.modules.authorizations.provisioning import (
    ActivationProvisioningContext,
    require_activation_provisioning,
)
from app.modules.authorizations.repository import AuthorizationRepository
from app.modules.authorizations.schemas import (
    AuthorizationCreate,
    AuthorizationReject,
    AuthorizationResponse,
    AuthorizationRevoke,
    AuthorizationUpdate,
)
from app.modules.authorizations.service import AuthorizationService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.platform.clock import Clock, get_clock
from app.platform.dependencies import get_session

router = APIRouter(tags=["authorizations"])


def _service(
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> AuthorizationService:
    return AuthorizationService(
        AuthorizationRepository(session),
        AssetRepository(session),
        ProjectRepository(session),
        OrganizationRepository(session),
        clock,
    )


@router.post(
    "/api/v1/projects/{project_id}/authorizations",
    status_code=status.HTTP_201_CREATED,
)
async def create_authorization(
    project_id: UUID,
    payload: AuthorizationCreate,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AuthorizationService = Depends(_service),
) -> AuthorizationResponse:
    authorization = await service.create(tenant, project_id, payload)
    return AuthorizationResponse.model_validate(authorization)


@router.get("/api/v1/projects/{project_id}/authorizations")
async def list_authorizations(
    project_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AuthorizationService = Depends(_service),
) -> list[AuthorizationResponse]:
    authorizations = await service.list_for_project(project_id, tenant)
    return [AuthorizationResponse.model_validate(auth) for auth in authorizations]


@router.get("/api/v1/authorizations/{authorization_id}")
async def get_authorization(
    authorization_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AuthorizationService = Depends(_service),
) -> AuthorizationResponse:
    authorization = await service.get_for_tenant(authorization_id, tenant)
    return AuthorizationResponse.model_validate(authorization)


@router.patch("/api/v1/authorizations/{authorization_id}")
async def update_authorization(
    authorization_id: UUID,
    payload: AuthorizationUpdate,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AuthorizationService = Depends(_service),
) -> AuthorizationResponse:
    authorization = await service.update(authorization_id, tenant, payload)
    return AuthorizationResponse.model_validate(authorization)


@router.post("/api/v1/authorizations/{authorization_id}/submit")
async def submit_authorization(
    authorization_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AuthorizationService = Depends(_service),
) -> AuthorizationResponse:
    authorization = await service.submit(authorization_id, tenant)
    return AuthorizationResponse.model_validate(authorization)


@router.post("/api/v1/authorizations/{authorization_id}/activate")
async def activate_authorization(
    authorization_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    provisioning: ActivationProvisioningContext = Depends(
        require_activation_provisioning
    ),
    service: AuthorizationService = Depends(_service),
) -> AuthorizationResponse:
    authorization = await service.activate(authorization_id, tenant, provisioning)
    return AuthorizationResponse.model_validate(authorization)


@router.post("/api/v1/authorizations/{authorization_id}/reject")
async def reject_authorization(
    authorization_id: UUID,
    payload: AuthorizationReject,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AuthorizationService = Depends(_service),
) -> AuthorizationResponse:
    authorization = await service.reject(authorization_id, tenant, payload)
    return AuthorizationResponse.model_validate(authorization)


@router.post("/api/v1/authorizations/{authorization_id}/revoke")
async def revoke_authorization(
    authorization_id: UUID,
    payload: AuthorizationRevoke,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AuthorizationService = Depends(_service),
) -> AuthorizationResponse:
    authorization = await service.revoke(authorization_id, tenant, payload)
    return AuthorizationResponse.model_validate(authorization)
