"""HTTP routes for validation executions. Thin: parse, authorize, delegate, map.

The API records intent and authorization and hands an immutable specification
to the dispatch seam. It never runs scanner logic inline.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.repository import AssetRepository
from app.modules.authorizations.repository import AuthorizationRepository
from app.modules.engagements.repository import EngagementRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.modules.validation_executions.credential_issuer import (
    PersistedWorkerCredentialIssuer,
)
from app.modules.validation_executions.credential_repository import (
    WorkerCredentialRepository,
)
from app.modules.validation_executions.dispatcher import (
    ValidationDispatcher,
    get_validation_dispatcher,
)
from app.modules.validation_executions.repository import (
    ValidationExecutionRepository,
)
from app.modules.validation_executions.schemas import (
    ValidationExecutionCreate,
    ValidationExecutionResponse,
    WorkerExecutionStateResponse,
    WorkerFinishedRequest,
)
from app.modules.validation_executions.service import ValidationExecutionService
from app.modules.validation_executions.worker_auth import (
    WorkerContext,
    require_worker_finished_context,
    require_worker_started_context,
)
from app.platform.clock import Clock, get_clock
from app.platform.dependencies import get_session

router = APIRouter(tags=["validation-executions"])


def _service(
    session: AsyncSession = Depends(get_session),
    dispatcher: ValidationDispatcher = Depends(get_validation_dispatcher),
    clock: Clock = Depends(get_clock),
) -> ValidationExecutionService:
    # One repository (and thus one session/transaction) is shared by the service
    # and the credential issuer, so a dispatch-time credential is minted in the
    # same transaction as the execution row — they commit or roll back together.
    executions = ValidationExecutionRepository(session)
    credential_issuer = PersistedWorkerCredentialIssuer(
        WorkerCredentialRepository(session),
        executions,
        clock,
    )
    return ValidationExecutionService(
        executions,
        EngagementRepository(session),
        AuthorizationRepository(session),
        AssetRepository(session),
        ProjectRepository(session),
        dispatcher,
        clock,
        credential_issuer,
        WorkerCredentialRepository(session),
    )


@router.post(
    "/api/v1/validation-executions",
    status_code=status.HTTP_201_CREATED,
)
async def create_validation_execution(
    payload: ValidationExecutionCreate,
    tenant: TenantContext = Depends(require_tenant_context),
    service: ValidationExecutionService = Depends(_service),
) -> ValidationExecutionResponse:
    # create_and_queue freezes the snapshots, persists the row, and hands the
    # frozen payload to the fail-closed dispatch seam in one transaction. The
    # worker pipeline never runs in this process.
    execution = await service.create_and_queue(tenant, payload)
    return ValidationExecutionResponse.model_validate(execution)


@router.get("/api/v1/validation-executions/{execution_id}")
async def get_validation_execution(
    execution_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: ValidationExecutionService = Depends(_service),
) -> ValidationExecutionResponse:
    execution = await service.get_for_tenant(execution_id, tenant)
    return ValidationExecutionResponse.model_validate(execution)


@router.get("/api/v1/projects/{project_id}/validation-executions")
async def list_validation_executions(
    project_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: ValidationExecutionService = Depends(_service),
) -> list[ValidationExecutionResponse]:
    executions = await service.list_for_project(project_id, tenant)
    return [
        ValidationExecutionResponse.model_validate(execution)
        for execution in executions
    ]


@router.post("/api/v1/validation-executions/{execution_id}/cancel")
async def cancel_validation_execution(
    execution_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: ValidationExecutionService = Depends(_service),
) -> ValidationExecutionResponse:
    execution = await service.cancel(execution_id, tenant)
    return ValidationExecutionResponse.model_validate(execution)


@router.post("/api/v1/validation-executions/{execution_id}/worker-started")
async def worker_started(
    execution_id: UUID,
    worker: WorkerContext = Depends(require_worker_started_context),
    service: ValidationExecutionService = Depends(_service),
) -> WorkerExecutionStateResponse:
    # Machine-authenticated against a per-execution credential bound to this
    # row (see ``worker_auth``). No tenant context. The service still derives
    # the organization from the locked row. The response is minimized so the
    # spec, snapshots, and kill-switch token are never echoed.
    execution = await service.worker_started(execution_id, worker)
    return WorkerExecutionStateResponse.model_validate(execution)


@router.post("/api/v1/validation-executions/{execution_id}/worker-finished")
async def worker_finished(
    execution_id: UUID,
    payload: WorkerFinishedRequest,
    worker: WorkerContext = Depends(require_worker_finished_context),
    service: ValidationExecutionService = Depends(_service),
) -> WorkerExecutionStateResponse:
    # Per-execution credential gated on the ``worker_finished`` action;
    # minimized response (see ``worker_started``). Step evidence is persisted
    # but never reflected back to the worker.
    execution = await service.worker_finished(execution_id, worker, payload)
    return WorkerExecutionStateResponse.model_validate(execution)
