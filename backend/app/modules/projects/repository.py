"""Data access for projects. Concrete and tenant-scoped; no generic base."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project


class ProjectRepository:
    """Reads and writes :class:`Project` rows on one session.

    Every read is scoped by ``organization_id`` so a project is never returned
    to a tenant that does not own it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, project: Project) -> None:
        self._session.add(project)
        await self._session.flush()
        await self._session.refresh(project)

    async def get_in_org(
        self, project_id: UUID, organization_id: UUID
    ) -> Project | None:
        result = await self._session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(self, organization_id: UUID) -> Sequence[Project]:
        result = await self._session.execute(
            select(Project)
            .where(Project.organization_id == organization_id)
            .order_by(Project.created_at)
        )
        return result.scalars().all()

    async def slug_exists_in_org(self, organization_id: UUID, slug: str) -> bool:
        result = await self._session.execute(
            select(Project.id)
            .where(
                Project.organization_id == organization_id,
                Project.slug == slug,
            )
            .limit(1)
        )
        return result.first() is not None
