"""Data access for engagements. Concrete and tenant-scoped; no generic base."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.engagements.enums import EngagementStatus
from app.modules.engagements.models import Engagement, EngagementScope


class EngagementRepository:
    """Reads and writes :class:`Engagement` rows on one session.

    Every read is scoped by ``organization_id`` so an engagement is never
    returned to a tenant that does not own it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, engagement: Engagement) -> None:
        self._session.add(engagement)
        await self._session.flush()
        await self._session.refresh(engagement)

    async def persist(self, engagement: Engagement) -> None:
        """Flush pending mutations and reload server-managed columns."""
        await self._session.flush()
        await self._session.refresh(engagement)

    async def get_in_org(
        self, engagement_id: UUID, organization_id: UUID
    ) -> Engagement | None:
        result = await self._session.execute(
            select(Engagement).where(
                Engagement.id == engagement_id,
                Engagement.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_in_org_for_update(
        self, engagement_id: UUID, organization_id: UUID
    ) -> Engagement | None:
        """Tenant-scoped fetch that locks the engagement row.

        Used to serialize concurrent transitions.
        """
        result = await self._session.execute(
            select(Engagement)
            .where(
                Engagement.id == engagement_id,
                Engagement.organization_id == organization_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_for_project(
        self, project_id: UUID, organization_id: UUID
    ) -> Sequence[Engagement]:
        result = await self._session.execute(
            select(Engagement)
            .where(
                Engagement.project_id == project_id,
                Engagement.organization_id == organization_id,
            )
            .order_by(Engagement.created_at.desc())
        )
        return result.scalars().all()

    async def conditional_transition(
        self,
        engagement_id: UUID,
        organization_id: UUID,
        expected_status: EngagementStatus,
        new_status: EngagementStatus,
        **extra_fields: object,
    ) -> bool:
        """Atomically update the status if it matches ``expected_status``.

        Returns ``True`` when exactly one row was updated; ``False`` when zero
        rows matched (concurrent transition already occurred).
        """
        values: dict[str, object] = {"status": new_status, **extra_fields}
        result = await self._session.execute(
            update(Engagement)
            .where(
                Engagement.id == engagement_id,
                Engagement.organization_id == organization_id,
                Engagement.status == expected_status,
            )
            .values(**values)
        )
        return cast("CursorResult[tuple[int]]", result).rowcount == 1

    async def replace_scopes(
        self, engagement: Engagement, scopes: list[EngagementScope]
    ) -> None:
        """Replace all scopes on the engagement with a new set.

        Assigning the relationship collection lets the ``all, delete-orphan``
        cascade remove the previous scopes and anchor each new scope to the
        engagement (setting its FK) on flush. Must run inside a transaction.
        """
        engagement.scopes = scopes
        await self._session.flush()
