"""Data access for audit events. Tenant-scoped, append-only."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit_events.models import AuditEvent


class AuditEventRepository:
    """Reads and writes :class:`AuditEvent` rows on one session.

    Every read is scoped by ``organization_id`` so an event is never
    returned to a tenant that does not own it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> None:
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)

    async def list_for_org(
        self, org_id: UUID, limit: int = 100
    ) -> Sequence[AuditEvent]:
        result = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.organization_id == org_id)
            .order_by(AuditEvent.at.desc())
            .limit(limit)
        )
        return result.scalars().all()
