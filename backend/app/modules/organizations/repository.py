"""Data access for organizations. Concrete and specific; no generic base."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization


class OrganizationRepository:
    """Reads and writes :class:`Organization` rows on one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> None:
        """Persist a new organization and load server-set columns."""
        self._session.add(organization)
        await self._session.flush()
        await self._session.refresh(organization)

    async def get(self, organization_id: UUID) -> Organization | None:
        return await self._session.get(Organization, organization_id)

    async def list_for_tenant(self, organization_id: UUID) -> list[Organization]:
        """Return the single organization the tenant belongs to."""
        result = await self._session.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        return list(result.scalars().all())

    async def slug_exists(self, slug: str) -> bool:
        result = await self._session.execute(
            select(Organization.id).where(Organization.slug == slug).limit(1)
        )
        return result.first() is not None
