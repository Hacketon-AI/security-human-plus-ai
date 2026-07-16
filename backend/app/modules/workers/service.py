"""Business logic for deriving worker and dispatch queue state."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.validation_executions.enums import ExecutionStatus
from app.modules.validation_executions.models import ValidationExecution
from app.modules.workers.schemas import DispatchQueueResponse, WorkerStateResponse

_QUEUE_NAME = "validation_executions"
_ROUTING_KEY = "validation.execute"
_REGION = "eu-1"


class WorkersService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_workers(self, org_id: UUID) -> list[WorkerStateResponse]:
        """Derive one WorkerStateResponse per active or recently-finished execution."""
        result = await self._session.execute(
            select(ValidationExecution)
            .where(
                ValidationExecution.organization_id == org_id,
                ValidationExecution.status.in_(
                    [
                        ExecutionStatus.executing,
                        ExecutionStatus.dispatching,
                        ExecutionStatus.queued,
                        ExecutionStatus.succeeded,
                        ExecutionStatus.failed,
                        ExecutionStatus.blocked,
                    ]
                ),
            )
            .order_by(ValidationExecution.updated_at.desc())
            .limit(20)
        )
        executions = result.scalars().all()

        workers: list[WorkerStateResponse] = []
        for ex in executions:
            if ex.status == ExecutionStatus.executing:
                state = "running"
            elif ex.status in (
                ExecutionStatus.succeeded,
                ExecutionStatus.failed,
                ExecutionStatus.blocked,
            ):
                state = "finished"
            else:
                state = "idle"

            short_id = str(ex.id)[:4]
            worker_id = f"wkr-{_REGION}-{short_id}"
            heartbeat = ex.updated_at.isoformat() if ex.updated_at else None
            exec_code = (
                f"EXEC-{ex.created_at.strftime('%Y%m%d')}-{short_id.upper()}"
                if ex.created_at
                else str(ex.id)[:8].upper()
            )

            workers.append(
                WorkerStateResponse(
                    worker_id=worker_id,
                    region=_REGION,
                    state=state,
                    current_execution_id=exec_code if state == "running" else None,
                    last_heartbeat=heartbeat,
                )
            )

        return workers

    async def get_dispatch_queue(self, org_id: UUID) -> DispatchQueueResponse:
        """Derive queue metrics from current execution status counts."""
        cutoff = datetime.now(UTC) - timedelta(hours=24)

        # Count all statuses for this org in one query
        result = await self._session.execute(
            select(ValidationExecution.status, func.count())
            .where(ValidationExecution.organization_id == org_id)
            .group_by(ValidationExecution.status)
        )
        counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

        # Failed/blocked only in last 24h
        failed_result = await self._session.execute(
            select(func.count())
            .select_from(ValidationExecution)
            .where(
                ValidationExecution.organization_id == org_id,
                ValidationExecution.status.in_(
                    [
                        ExecutionStatus.failed,
                        ExecutionStatus.blocked,
                    ]
                ),
                ValidationExecution.updated_at >= cutoff,
            )
        )
        failed_24h = failed_result.scalar_one_or_none() or 0

        pending = counts.get(ExecutionStatus.queued, 0) + counts.get(
            ExecutionStatus.dispatching, 0
        )
        active = counts.get(ExecutionStatus.executing, 0)

        return DispatchQueueResponse(
            queue_name=_QUEUE_NAME,
            routing_key=_ROUTING_KEY,
            broker_status="online",
            pending=pending,
            active=active,
            failed=failed_24h,
        )
