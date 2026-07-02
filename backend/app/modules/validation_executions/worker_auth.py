"""Worker transition authentication for validation executions.

Each call to ``worker-started`` / ``worker-finished`` authenticates the
caller as a *machine* — never as a tenant user — and the credential is
*per-execution*: a row in ``validation_worker_credentials`` whose digest
matches the presented token and whose scope (execution_id, action,
expiry, revocation) is satisfied. The tenant ``X-Organization-Id``
header is never consulted on this path; the organization is derived from
the credential's persisted row, which is itself bound to the execution
(see ``docs/validation-worker-credentials-design.md``).

A transitional shared-token fallback (``Settings.worker_auth_token``) is
preserved behind an explicit, off-by-default flag
(``Settings.worker_shared_token_fallback_enabled``). When enabled, the
shared token authenticates *only* if no per-execution credential matched
the presented digest; a digest match that fails the per-execution scope
*never* falls through to the shared token. Every shared-token success
emits a deprecation warning to the worker-auth log (the token value
itself is never logged).

All failure modes — missing header, wrong digest, wrong execution,
wrong action, expired, revoked, fallback disabled — produce the same
content-free :class:`WorkerAuthenticationFailed` so a caller cannot
distinguish "wrong" from "not configured".
"""

import hmac
import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.validation_executions.credential_repository import (
    WorkerCredentialRepository,
)
from app.modules.validation_executions.credential_verifier import (
    PersistedWorkerCredentialVerifier,
)
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialVerificationOutcome,
    WorkerHookAction,
    compute_worker_token_digest,
)
from app.platform.clock import Clock, get_clock
from app.platform.dependencies import get_app_settings, get_session
from app.platform.errors import AuthenticationRequiredError

_WORKER_AUTH_HEADER = "X-Worker-Authorization"

# Audit ``actor`` value for the shared-token fallback path. A constant rather
# than the (sensitive) token value or the (PII-shaped) organization, so audit
# events remain readable without leaking either.
_FALLBACK_WORKER_REFERENCE = "shared-token-fallback"

# Audit ``actor`` for a per-execution credential when the verifier reports no
# credential_id (defensive only; ``accepted`` always carries one).
_DEFAULT_WORKER_REFERENCE = "worker"

_logger = logging.getLogger("securescope.validation.worker_auth")


@dataclass(frozen=True, slots=True)
class WorkerContext:
    """The authenticated worker calling a transition hook.

    Populated from the verifier's outcome or the shared-token fallback:

    * ``execution_id`` — the row this hook is mutating; mirrors the path.
    * ``organization_id`` — the credential's tenant binding, or ``None``
      for the shared-token fallback (the legacy single-token path has no
      per-tenant binding; the service derives the org from the locked row
      regardless).
    * ``credential_id`` — the per-execution credential id; ``None`` on the
      fallback path.
    * ``action`` — the hook this context authorized.
    * ``worker_reference`` — opaque, non-sensitive audit actor. Set to
      the credential id when present, ``"shared-token-fallback"`` for the
      legacy path, and ``"worker"`` only as a defensive default.
    """

    execution_id: UUID
    organization_id: UUID | None
    credential_id: str | None
    action: WorkerHookAction
    worker_reference: str


class WorkerAuthenticationFailed(AuthenticationRequiredError):
    """Worker authentication failed.

    Raised for a missing credential, an invalid credential, an expired or
    revoked credential, a credential for a different execution / action,
    or a shared token presented when the fallback is disabled. The cases
    are intentionally indistinguishable to the caller, so the error never
    says which occurred.
    """

    code = "worker_authentication_failed"


async def _authenticate(
    *,
    action: WorkerHookAction,
    execution_id: UUID,
    x_worker_authorization: str | None,
    session: AsyncSession,
    settings: Settings,
    clock: Clock,
) -> WorkerContext:
    """Resolve the WorkerContext for one hook call.

    Verification order:

    1. Missing header → fail closed.
    2. Look up the credential row by digest. If a row matches, evaluate
       the full scope (execution / action / revoke / expiry). On
       acceptance return the authenticated context. **No** fall-through
       to the shared token: a digest hit that fails scope is final.
    3. Otherwise, if the shared-token fallback is explicitly enabled and
       the configured token matches in constant time, log a deprecation
       warning (no token value) and return a fallback context.
    4. Anything else → fail closed.
    """
    if not x_worker_authorization:
        raise WorkerAuthenticationFailed("worker authentication failed")

    repo = WorkerCredentialRepository(session)
    digest = compute_worker_token_digest(x_worker_authorization)
    row = await repo.get_by_token_digest(digest)
    if row is not None:
        verifier = PersistedWorkerCredentialVerifier(repo, clock)
        result = await verifier.verify(
            presented_token=SecretStr(x_worker_authorization),
            expected_execution_id=str(execution_id),
            # The credential row's organization is the row's recorded tenant.
            # ``evaluate_worker_credential`` checks equality, so this layer
            # cannot accidentally widen the grant: the row's own column is
            # the authoritative source.
            expected_organization_id=str(row.organization_id),
            action=action,
        )
        if result.outcome is WorkerCredentialVerificationOutcome.accepted:
            return WorkerContext(
                execution_id=execution_id,
                organization_id=row.organization_id,
                credential_id=result.credential_id,
                action=action,
                worker_reference=(
                    result.credential_id
                    if result.credential_id is not None
                    else _DEFAULT_WORKER_REFERENCE
                ),
            )
        # Digest matched but scope failed — never fall back to the shared
        # token, even when the operator enabled it. Otherwise an attacker
        # with a credential for execution A could trade it for shared-token
        # access to execution B.
        raise WorkerAuthenticationFailed("worker authentication failed")

    # No per-execution credential matched. Try the explicit transitional
    # fallback if the operator enabled it. Both checks below are required:
    # the flag alone, with no configured token, is not a working path.
    configured = settings.worker_auth_token
    if (
        settings.worker_shared_token_fallback_enabled
        and configured is not None
        and hmac.compare_digest(
            configured.get_secret_value().encode("utf-8"),
            x_worker_authorization.encode("utf-8"),
        )
    ):
        _logger.warning(
            "deprecated shared worker_auth_token accepted for execution %s action %s",
            execution_id,
            action.value,
        )
        return WorkerContext(
            execution_id=execution_id,
            organization_id=None,
            credential_id=None,
            action=action,
            worker_reference=_FALLBACK_WORKER_REFERENCE,
        )

    raise WorkerAuthenticationFailed("worker authentication failed")


async def require_worker_started_context(
    execution_id: UUID,
    x_worker_authorization: str | None = Header(
        default=None, alias=_WORKER_AUTH_HEADER
    ),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    clock: Clock = Depends(get_clock),
) -> WorkerContext:
    """FastAPI dependency: authenticate the ``worker-started`` hook."""
    return await _authenticate(
        action=WorkerHookAction.worker_started,
        execution_id=execution_id,
        x_worker_authorization=x_worker_authorization,
        session=session,
        settings=settings,
        clock=clock,
    )


async def require_worker_finished_context(
    execution_id: UUID,
    x_worker_authorization: str | None = Header(
        default=None, alias=_WORKER_AUTH_HEADER
    ),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    clock: Clock = Depends(get_clock),
) -> WorkerContext:
    """FastAPI dependency: authenticate the ``worker-finished`` hook."""
    return await _authenticate(
        action=WorkerHookAction.worker_finished,
        execution_id=execution_id,
        x_worker_authorization=x_worker_authorization,
        session=session,
        settings=settings,
        clock=clock,
    )
