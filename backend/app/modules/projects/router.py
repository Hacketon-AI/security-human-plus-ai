"""HTTP routes for projects. Thin: parse, authorize, delegate, map."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate, ProjectResponse
from app.modules.projects.service import ProjectService
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.platform.dependencies import get_session

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _service(session: AsyncSession = Depends(get_session)) -> ProjectService:
    return ProjectService(
        ProjectRepository(session),
        OrganizationRepository(session),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    tenant: TenantContext = Depends(require_tenant_context),
    service: ProjectService = Depends(_service),
) -> ProjectResponse:
    project = await service.create(tenant, payload)
    return ProjectResponse.model_validate(project)


@router.get("")
async def list_projects(
    tenant: TenantContext = Depends(require_tenant_context),
    service: ProjectService = Depends(_service),
) -> list[ProjectResponse]:
    projects = await service.list_for_tenant(tenant)
    return [ProjectResponse.model_validate(project) for project in projects]


@router.get("/{project_id}")
async def get_project(
    project_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: ProjectService = Depends(_service),
) -> ProjectResponse:
    project = await service.get_for_tenant(project_id, tenant)
    return ProjectResponse.model_validate(project)
