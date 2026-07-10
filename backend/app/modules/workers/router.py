"""HTTP routes for workers and dispatch queues. Thin: parse, authorize, delegate, map."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.modules.workers.schemas import DispatchQueueResponse, WorkerStateResponse
from app.modules.workers.service import WorkersService
from app.platform.dependencies import get_session

router = APIRouter(tags=["workers"])


def _service(session: AsyncSession = Depends(get_session)) -> WorkersService:
    return WorkersService(session)


@router.get("/api/v1/workers")
async def list_workers(
    tenant: TenantContext = Depends(require_tenant_context),
    service: WorkersService = Depends(_service),
) -> list[WorkerStateResponse]:
    """List derived worker states for the authenticated tenant's executions."""
    return await service.list_workers(tenant.organization_id)


@router.get("/api/v1/dispatch-queues")
async def list_dispatch_queues(
    tenant: TenantContext = Depends(require_tenant_context),
    service: WorkersService = Depends(_service),
) -> list[DispatchQueueResponse]:
    """Return derived dispatch queue metrics for the authenticated tenant."""
    queue = await service.get_dispatch_queue(tenant.organization_id)
    return [queue]
