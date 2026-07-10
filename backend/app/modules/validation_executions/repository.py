"""Data access for validation executions. Concrete and tenant-scoped."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.validation_executions.enums import ExecutionStatus
from app.modules.validation_executions.models import ValidationExecution


class ValidationExecutionRepository:
    """Reads and writes :class:`ValidationExecution` rows on one session.

    Every read is scoped by ``organization_id`` so an execution is never
    returned to a tenant that does not own it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, execution: ValidationExecution) -> None:
        self._session.add(execution)
        await self._session.flush()
        await self._session.refresh(execution)

    async def persist(self, execution: ValidationExecution) -> None:
        """Flush pending mutations and reload server-managed columns."""
        await self._session.flush()
        await self._session.refresh(execution)

    async def get_in_org(
        self, execution_id: UUID, organization_id: UUID
    ) -> ValidationExecution | None:
        result = await self._session.execute(
            select(ValidationExecution).where(
                ValidationExecution.id == execution_id,
                ValidationExecution.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_in_org_for_update(
        self, execution_id: UUID, organization_id: UUID
    ) -> ValidationExecution | None:
        """Tenant-scoped fetch that locks the execution row for transitions."""
        result = await self._session.execute(
            select(ValidationExecution)
            .where(
                ValidationExecution.id == execution_id,
                ValidationExecution.organization_id == organization_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, execution_id: UUID) -> ValidationExecution | None:
        """Fetch and lock an execution by id alone, for machine worker hooks.

        Worker transition hooks authenticate at the machine level and identify
        the row by its unforgeable execution id, so they are not tenant-scoped:
        the organization is read from the row itself. User-facing reads must keep
        using the ``*_in_org`` variants so one tenant never sees another's rows.
        """
        result = await self._session.execute(
            select(ValidationExecution)
            .where(ValidationExecution.id == execution_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, execution_id: UUID) -> ValidationExecution | None:
        """Fetch an execution by id alone, without a lock, for machine reads.

        Used by the kill-switch poll, which authenticates on the frozen
        ``kill_switch_token`` (not a tenant) and only reads state — so it must
        not take the row lock ``get_for_update`` holds (polls are frequent and
        must not serialize behind a running transition). The organization is
        read from the row, never the caller. User-facing reads keep using the
        ``*_in_org`` variants so one tenant never sees another's rows.
        """
        result = await self._session.execute(
            select(ValidationExecution).where(ValidationExecution.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> ValidationExecution | None:
        result = await self._session.execute(
            select(ValidationExecution).where(
                ValidationExecution.organization_id == organization_id,
                ValidationExecution.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self,
        org_id: UUID,
        statuses: list[ExecutionStatus] | None = None,
    ) -> Sequence[ValidationExecution]:
        stmt = select(ValidationExecution).where(
            ValidationExecution.organization_id == org_id,
        )
        if statuses:
            stmt = stmt.where(ValidationExecution.status.in_(statuses))
        stmt = stmt.order_by(ValidationExecution.created_at.desc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_for_project(
        self, project_id: UUID, organization_id: UUID
    ) -> Sequence[ValidationExecution]:
        result = await self._session.execute(
            select(ValidationExecution)
            .where(
                ValidationExecution.project_id == project_id,
                ValidationExecution.organization_id == organization_id,
            )
            .order_by(ValidationExecution.created_at.desc())
        )
        return result.scalars().all()

    async def conditional_transition(
        self,
        execution_id: UUID,
        organization_id: UUID,
        expected_status: ExecutionStatus,
        new_status: ExecutionStatus,
        **extra_fields: object,
    ) -> bool:
        """Atomically update the status if it matches ``expected_status``.

        Returns ``True`` when exactly one row was updated; ``False`` when zero
        rows matched (a concurrent transition already occurred).
        """
        values: dict[str, object] = {"status": new_status, **extra_fields}
        result = await self._session.execute(
            update(ValidationExecution)
            .where(
                ValidationExecution.id == execution_id,
                ValidationExecution.organization_id == organization_id,
                ValidationExecution.status == expected_status,
            )
            .values(**values)
        )
        return cast("CursorResult[tuple[int]]", result).rowcount == 1
