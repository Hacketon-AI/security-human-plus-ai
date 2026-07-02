"""Concrete per-execution worker credential issuer (persisted).

Mints a fresh per-execution credential at dispatch time, persists *only*
the SHA-256 digest, and hands the raw token back to the caller exactly
once via :class:`IssuedWorkerCredential`. This is the persistence-backed
implementation of the :class:`WorkerCredentialIssuer` Protocol defined in
:mod:`worker_credential_contracts` (Step 2 of
``docs/validation-worker-credentials-design.md``).

The issuer is the only point in the codebase that holds the raw token, and
even there only inside the returned :class:`IssuedWorkerCredential` —
nothing about the token survives the function call beyond what the caller
explicitly retains. Logs reference the assigned ``credential_id`` only.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.modules.validation_executions.credential_repository import (
    WorkerCredentialRepository,
)
from app.modules.validation_executions.enums import ExecutionStatus
from app.modules.validation_executions.models import ValidationWorkerCredential
from app.modules.validation_executions.repository import (
    ValidationExecutionRepository,
)
from app.modules.validation_executions.worker_credential_contracts import (
    IssuedWorkerCredential,
    WorkerCredentialGrant,
    WorkerCredentialIssueOutcome,
    WorkerCredentialIssueResult,
    WorkerHookAction,
    compute_worker_token_digest,
    generate_worker_token,
)
from app.platform.clock import Clock

# Hard cap for ``expires_at``. The design doc fixes 24 h as the upper bound
# even if a caller passes a longer TTL — keeps the blast radius of a leaked
# token bounded by the engagement window.
DEFAULT_CREDENTIAL_HARD_TTL = timedelta(hours=24)

# Statuses an execution may be in when a credential is minted. A terminal
# execution should never accept a fresh credential — the worker pipeline
# for it is over.
_ISSUABLE_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {
        ExecutionStatus.queued,
        ExecutionStatus.dispatching,
        ExecutionStatus.executing,
    }
)

_logger = logging.getLogger("securescope.validation.credential_issuer")


class PersistedWorkerCredentialIssuer:
    """Mint per-execution worker credentials backed by PostgreSQL.

    Implements :class:`WorkerCredentialIssuer`. Verifies the target
    execution exists and is in an issuable state, enforces the
    ``allowed_actions`` and TTL rules, persists the digest, and returns
    the raw token exactly once.
    """

    def __init__(
        self,
        credentials: WorkerCredentialRepository,
        executions: ValidationExecutionRepository,
        clock: Clock,
        *,
        hard_ttl: timedelta = DEFAULT_CREDENTIAL_HARD_TTL,
    ) -> None:
        self._credentials = credentials
        self._executions = executions
        self._clock = clock
        self._hard_ttl = hard_ttl

    async def issue(
        self,
        *,
        execution_id: str,
        organization_id: str,
        allowed_actions: frozenset[WorkerHookAction],
        expires_at: datetime,
    ) -> WorkerCredentialIssueResult:
        """Mint, persist, and return one credential — or refuse safely.

        Refusal categories (always typed, never a raw exception or value):

        * ``empty_actions`` — empty ``allowed_actions``.
        * ``invalid_expiry`` — ``expires_at`` not in the future, or beyond
          the configured hard TTL cap.
        * ``execution_not_found`` — no row matches the supplied tenant.
        * ``execution_not_issuable`` — row exists but is in a terminal
          state.

        The raw token never appears in logs, in the rejection result, or
        anywhere outside the returned :class:`IssuedWorkerCredential`.
        """
        if not allowed_actions:
            return _rejected("empty_actions")

        now = self._clock.now()
        if expires_at <= now:
            return _rejected("invalid_expiry")
        if expires_at - now > self._hard_ttl:
            return _rejected("invalid_expiry")

        execution_uuid = _parse_uuid(execution_id)
        organization_uuid = _parse_uuid(organization_id)
        if execution_uuid is None or organization_uuid is None:
            return _rejected("execution_not_found")

        execution = await self._executions.get_in_org(execution_uuid, organization_uuid)
        if execution is None:
            return _rejected("execution_not_found")
        if execution.status not in _ISSUABLE_STATUSES:
            return _rejected("execution_not_issuable")

        raw_token = generate_worker_token()
        token_digest = compute_worker_token_digest(raw_token.get_secret_value())

        credential = ValidationWorkerCredential(
            id=uuid4(),
            organization_id=execution.organization_id,
            execution_id=execution.id,
            token_digest=token_digest,
            allowed_actions=sorted(action.value for action in allowed_actions),
            issued_at=now,
            expires_at=expires_at,
            revoked_at=None,
        )
        await self._credentials.add(credential)

        grant = WorkerCredentialGrant(
            credential_id=str(credential.id),
            organization_id=str(credential.organization_id),
            execution_id=str(credential.execution_id),
            token_digest=credential.token_digest,
            allowed_actions=frozenset(allowed_actions),
            issued_at=credential.issued_at,
            expires_at=credential.expires_at,
            revoked_at=credential.revoked_at,
        )
        _logger.info(
            "issued worker credential %s for execution %s",
            credential.id,
            credential.execution_id,
        )
        return WorkerCredentialIssueResult(
            outcome=WorkerCredentialIssueOutcome.issued,
            issued=IssuedWorkerCredential(grant=grant, raw_token=raw_token),
        )


def _rejected(failure: str) -> WorkerCredentialIssueResult:
    """Build a rejected result with a short safe failure category."""
    return WorkerCredentialIssueResult(
        outcome=WorkerCredentialIssueOutcome.rejected,
        failure=failure,
    )


def _parse_uuid(candidate: str) -> UUID | None:
    """Best-effort UUID parse; returns ``None`` for anything malformed.

    A malformed id from the caller is normalised to ``execution_not_found``
    so the issuer never raises through the dispatch path; this matches the
    "fail closed" rule from ``CLAUDE.md``.
    """
    try:
        return UUID(candidate)
    except (ValueError, AttributeError, TypeError):
        return None
