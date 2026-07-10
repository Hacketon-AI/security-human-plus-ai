"""HTTP routes for organizations. Thin: parse, authorize, delegate, map."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import (
    OrganizationCreate,
    OrganizationResponse,
)
from app.modules.organizations.service import OrganizationService
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.modules.tenancy.provisioning import ProvisioningContext, require_provisioning
from app.platform.dependencies import get_session

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


def _service(session: AsyncSession = Depends(get_session)) -> OrganizationService:
    return OrganizationService(OrganizationRepository(session))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    # Provisioning is authorized separately from tenant authentication; it does
    # not use the tenant header because no organization exists yet.
    provisioning: ProvisioningContext = Depends(require_provisioning),
    service: OrganizationService = Depends(_service),
) -> OrganizationResponse:
    """Bootstrap a tenant root. Gated by provisioning authorization."""
    organization = await service.create(payload)
    return OrganizationResponse.model_validate(organization)


@router.get("")
async def list_organizations(
    tenant: TenantContext = Depends(require_tenant_context),
    service: OrganizationService = Depends(_service),
) -> list[OrganizationResponse]:
    """List organizations visible to the authenticated tenant (always one)."""
    organizations = await service.list_for_tenant(tenant)
    return [OrganizationResponse.model_validate(o) for o in organizations]


@router.get("/{organization_id}")
async def get_organization(
    organization_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: OrganizationService = Depends(_service),
) -> OrganizationResponse:
    organization = await service.get_for_tenant(organization_id, tenant)
    return OrganizationResponse.model_validate(organization)
