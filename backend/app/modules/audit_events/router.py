"""HTTP routes for audit events. Thin: parse, authorize, delegate, map."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit_events.repository import AuditEventRepository
from app.modules.audit_events.schemas import AuditEventResponse
from app.modules.audit_events.service import AuditEventService
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.platform.dependencies import get_session

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit-events"])


def _service(session: AsyncSession = Depends(get_session)) -> AuditEventService:
    return AuditEventService(AuditEventRepository(session))


@router.get("")
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    tenant: TenantContext = Depends(require_tenant_context),
    service: AuditEventService = Depends(_service),
) -> list[AuditEventResponse]:
    """List recent audit events for the authenticated tenant, newest first."""
    events = await service.list_for_tenant(tenant, limit=limit)
    return [AuditEventResponse.model_validate(e) for e in events]
