"""Project use cases.

Enforces tenant ownership and the organization-lifecycle gate for new projects,
plus per-tenant slug uniqueness.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.modules.organizations.enums import OrganizationStatus
from app.modules.organizations.errors import (
    OrganizationNotAcceptingProjects,
    OrganizationNotFound,
)
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.enums import ProjectStatus
from app.modules.projects.errors import ProjectNotFound, ProjectSlugConflict
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate
from app.modules.shared.persistence import unique_violation_constraint
from app.modules.shared.slug import normalize_slug, slugify
from app.modules.tenancy.context import TenantContext

_NOT_FOUND = "project not found"
_TENANT_NOT_FOUND = "organization not found"
# The unique constraint that backs per-organization project slug uniqueness.
_SLUG_CONSTRAINT = "uq_project_org_slug"


class ProjectService:
    """Creates and reads projects within an authenticated tenant."""

    def __init__(
        self,
        projects: ProjectRepository,
        organizations: OrganizationRepository,
    ) -> None:
        self._projects = projects
        self._organizations = organizations

    async def create(self, tenant: TenantContext, payload: ProjectCreate) -> Project:
        organization = await self._organizations.get(tenant.organization_id)
        if organization is None:
            raise OrganizationNotFound(_TENANT_NOT_FOUND)
        if organization.status is not OrganizationStatus.active:
            raise OrganizationNotAcceptingProjects(
                f"organization status {organization.status.value} "
                "cannot accept new projects"
            )

        slug = normalize_slug(payload.slug) if payload.slug else slugify(payload.name)
        if await self._projects.slug_exists_in_org(tenant.organization_id, slug):
            raise ProjectSlugConflict(
                f"project slug already in use in this organization: {slug}"
            )

        project = Project(
            organization_id=tenant.organization_id,
            name=payload.name.strip(),
            slug=slug,
            description=payload.description,
            status=ProjectStatus.active,
        )
        try:
            await self._projects.add(project)
        except IntegrityError as exc:
            # Covers the race past the pre-check above; only the project-slug
            # constraint becomes a conflict, other integrity errors stay safe
            # internal errors.
            if unique_violation_constraint(exc) == _SLUG_CONSTRAINT:
                raise ProjectSlugConflict(
                    f"project slug already in use in this organization: {slug}"
                ) from exc
            raise
        return project

    async def list_for_tenant(self, tenant: TenantContext) -> Sequence[Project]:
        return await self._projects.list_for_org(tenant.organization_id)

    async def get_for_tenant(self, project_id: UUID, tenant: TenantContext) -> Project:
        project = await self._projects.get_in_org(project_id, tenant.organization_id)
        if project is None:
            raise ProjectNotFound(_NOT_FOUND)
        return project
