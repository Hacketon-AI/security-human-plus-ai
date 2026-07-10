"""Business logic for audit events."""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from app.modules.audit_events.models import AuditEvent
from app.modules.audit_events.repository import AuditEventRepository
from app.modules.audit_events.schemas import AuditEventCreate
from app.modules.tenancy.context import TenantContext


class AuditEventService:
    def __init__(self, repo: AuditEventRepository) -> None:
        self._repo = repo

    async def record(self, org_id: UUID, payload: AuditEventCreate) -> AuditEvent:
        event = AuditEvent(
            id=uuid.uuid4(),
            organization_id=org_id,
            at=datetime.now(timezone.utc),
            actor=payload.actor,
            actor_type=payload.actor_type,
            action=payload.action,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            execution_id=payload.execution_id,
            safe_metadata=payload.safe_metadata,
        )
        await self._repo.add(event)
        return event

    async def list_for_tenant(
        self, tenant: TenantContext, limit: int = 100
    ) -> Sequence[AuditEvent]:
        return await self._repo.list_for_org(tenant.organization_id, limit=limit)
