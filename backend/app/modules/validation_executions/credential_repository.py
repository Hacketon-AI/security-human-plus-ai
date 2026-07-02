"""Persistence for per-execution worker credentials.

A small, focused data-access layer for :class:`ValidationWorkerCredential`.
The repository never accepts, returns, or persists a raw token — it works
entirely in digest space (see ``compute_worker_token_digest``). Reads cross
tenants only on the verifier's digest lookup, which is then constrained by
the contract evaluator's organization-boundary check before any decision is
made (see ``evaluate_worker_credential``).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.validation_executions.models import ValidationWorkerCredential


class WorkerCredentialRepository:
    """Reads and writes :class:`ValidationWorkerCredential` rows on one session.

    Methods are intentionally narrow. No "list all" / "find any" helper
    exists; the verifier looks rows up only by their unique digest, and
    administrative reads are tenant-scoped via ``execution_id``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, credential: ValidationWorkerCredential) -> None:
        """Persist a fresh credential row.

        The caller is responsible for setting ``token_digest`` (never the
        raw token), ``allowed_actions``, ``issued_at``, ``expires_at``. The
        ``id`` defaults to a fresh ``uuid4``; ``created_at`` / ``updated_at``
        are server-managed.
        """
        self._session.add(credential)
        await self._session.flush()
        await self._session.refresh(credential)

    async def get_by_token_digest(
        self, token_digest: str
    ) -> ValidationWorkerCredential | None:
        """Look up a row by digest; ``None`` when no match.

        This is the only read that is *not* tenant-scoped — the verifier
        does not yet know the tenant when it parses the header. Every check
        downstream (organization, execution, action, expiry, revocation)
        runs against the returned row's columns, never the caller's, so
        cross-tenant disclosure is impossible.
        """
        result = await self._session.execute(
            select(ValidationWorkerCredential).where(
                ValidationWorkerCredential.token_digest == token_digest,
            )
        )
        return result.scalar_one_or_none()

    async def list_active_for_execution(
        self,
        execution_id: UUID,
        organization_id: UUID,
        *,
        now: datetime,
    ) -> Sequence[ValidationWorkerCredential]:
        """Return non-revoked, non-expired credentials for one execution.

        Tenant-scoped: a row that does not belong to the supplied
        organization is invisible. Used by the issuer to detect duplicate
        issuance and by the operator UI to surface live credentials.
        """
        result = await self._session.execute(
            select(ValidationWorkerCredential)
            .where(
                ValidationWorkerCredential.execution_id == execution_id,
                ValidationWorkerCredential.organization_id == organization_id,
                ValidationWorkerCredential.revoked_at.is_(None),
                ValidationWorkerCredential.expires_at > now,
            )
            .order_by(ValidationWorkerCredential.issued_at.desc())
        )
        return result.scalars().all()

    async def revoke_for_execution(
        self,
        execution_id: UUID,
        organization_id: UUID,
        *,
        revoked_at: datetime,
    ) -> int:
        """Mark every active credential for one execution as revoked.

        Returns the number of rows affected. Idempotent: a credential
        already carrying a ``revoked_at`` is skipped, so a re-issued
        revocation does not move the timestamp forward.
        """
        result = await self._session.execute(
            update(ValidationWorkerCredential)
            .where(
                ValidationWorkerCredential.execution_id == execution_id,
                ValidationWorkerCredential.organization_id == organization_id,
                ValidationWorkerCredential.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        return cast("CursorResult[tuple[int]]", result).rowcount
