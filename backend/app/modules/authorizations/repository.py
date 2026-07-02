"""Data access for authorizations. Concrete and tenant-scoped; no generic base."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.authorizations.enums import AuthorizationStatus
from app.modules.authorizations.models import Authorization, AuthorizationScope


class AuthorizationRepository:
    """Reads and writes :class:`Authorization` rows on one session.

    Every read is scoped by ``organization_id`` so an authorization is never
    returned to a tenant that does not own it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, authorization: Authorization) -> None:
        self._session.add(authorization)
        await self._session.flush()
        await self._session.refresh(authorization)

    async def persist(self, authorization: Authorization) -> None:
        """Flush pending mutations and reload server-managed columns."""
        await self._session.flush()
        await self._session.refresh(authorization)

    async def get_in_org(
        self, authorization_id: UUID, organization_id: UUID
    ) -> Authorization | None:
        result = await self._session.execute(
            select(Authorization).where(
                Authorization.id == authorization_id,
                Authorization.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_in_org_for_update(
        self, authorization_id: UUID, organization_id: UUID
    ) -> Authorization | None:
        """Tenant-scoped fetch that locks the authorization row.

        Used to serialize concurrent transitions (submit/activate/revoke).
        """
        result = await self._session.execute(
            select(Authorization)
            .where(
                Authorization.id == authorization_id,
                Authorization.organization_id == organization_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_for_project(
        self, project_id: UUID, organization_id: UUID
    ) -> Sequence[Authorization]:
        result = await self._session.execute(
            select(Authorization)
            .where(
                Authorization.project_id == project_id,
                Authorization.organization_id == organization_id,
            )
            .order_by(Authorization.created_at.desc())
        )
        return result.scalars().all()

    async def conditional_transition(
        self,
        authorization_id: UUID,
        organization_id: UUID,
        expected_status: AuthorizationStatus,
        new_status: AuthorizationStatus,
        **extra_fields: object,
    ) -> bool:
        """Atomically update the status if it matches ``expected_status``.

        Returns ``True`` when exactly one row was updated; ``False`` when zero
        rows matched (concurrent transition already occurred). Used as the
        concurrency-safe transition primitive for submit/activate/revoke.
        """
        values: dict[str, object] = {"status": new_status, **extra_fields}
        result = await self._session.execute(
            update(Authorization)
            .where(
                Authorization.id == authorization_id,
                Authorization.organization_id == organization_id,
                Authorization.status == expected_status,
            )
            .values(**values)
        )
        return cast("CursorResult[tuple[int]]", result).rowcount == 1

    async def replace_scopes(
        self, authorization: Authorization, scopes: list[AuthorizationScope]
    ) -> None:
        """Replace all scopes on the authorization with a new set.

        Done as two flushes — remove the existing scopes, then add the new ones —
        rather than a single collection assignment. A replacement may reuse an
        existing ``(authorization_id, asset_id)`` pair, and that pair is unique
        (``uq_authorization_scope_asset``). A single flush can emit the INSERT for
        the reused pair before the DELETE of the old row, transiently violating
        the constraint; deleting first closes that window. The ``all,
        delete-orphan`` cascade performs the removals and anchors each new scope's
        FK to the authorization. Must run inside a transaction.
        """
        authorization.scopes.clear()
        await self._session.flush()
        authorization.scopes = scopes
        await self._session.flush()
