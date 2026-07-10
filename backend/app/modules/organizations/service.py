"""Organization use cases.

Holds the domain logic kept out of routers, Pydantic validators, and ORM
models: slug resolution, uniqueness, and tenant-scoped reads.
"""

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.modules.organizations.enums import OrganizationStatus
from app.modules.organizations.errors import (
    OrganizationNotFound,
    OrganizationSlugConflict,
)
from app.modules.organizations.models import Organization
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationCreate
from app.modules.shared.persistence import unique_violation_constraint
from app.modules.shared.slug import normalize_slug, slugify
from app.modules.tenancy.context import TenantContext

# A generic message so cross-tenant probing cannot distinguish "not yours" from
# "does not exist".
_NOT_FOUND = "organization not found"
# The unique constraint that backs organization slug uniqueness.
_SLUG_CONSTRAINT = "uq_organization_slug"


class OrganizationService:
    """Creates organizations and resolves them for an authenticated tenant."""

    def __init__(self, organizations: OrganizationRepository) -> None:
        self._organizations = organizations

    async def create(self, payload: OrganizationCreate) -> Organization:
        slug = normalize_slug(payload.slug) if payload.slug else slugify(payload.name)
        if await self._organizations.slug_exists(slug):
            raise OrganizationSlugConflict(f"organization slug already in use: {slug}")
        organization = Organization(
            name=payload.name.strip(),
            slug=slug,
            status=OrganizationStatus.active,
        )
        try:
            await self._organizations.add(organization)
        except IntegrityError as exc:
            # The pre-check above handles the common case; this covers the race
            # where a concurrent transaction commits the same slug first. Only
            # the slug constraint becomes a conflict — anything else is left to
            # surface as a safe internal error.
            if unique_violation_constraint(exc) == _SLUG_CONSTRAINT:
                raise OrganizationSlugConflict(
                    f"organization slug already in use: {slug}"
                ) from exc
            raise
        return organization

    async def get_for_tenant(
        self, organization_id: UUID, tenant: TenantContext
    ) -> Organization:
        """Return the organization only if it is the caller's own tenant."""
        if organization_id != tenant.organization_id:
            raise OrganizationNotFound(_NOT_FOUND)
        organization = await self._organizations.get(organization_id)
        if organization is None:
            raise OrganizationNotFound(_NOT_FOUND)
        return organization

    async def list_for_tenant(self, tenant: TenantContext) -> list[Organization]:
        """Return the tenant's own organization as a single-element list."""
        return await self._organizations.list_for_tenant(tenant.organization_id)
