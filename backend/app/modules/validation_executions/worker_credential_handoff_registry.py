"""Development/test in-memory registry for worker credential handoffs.

The dispatch path mints a per-execution credential and produces a
:class:`WorkerCredentialHandoff` carrying the raw token. In a real
deployment that handoff reaches the worker through an operational
side-channel (a per-execution container secret, a locked-down credential
service). This module is the *dev/test* stand-in for that side-channel: an
in-process registry that stores handoffs by ``execution_id`` and hands the
raw token to a worker bootstrap on request.

It is **not** production storage. It keeps everything in process memory,
never serializes a token to JSON, never logs a token, and consumes each
handoff exactly once (so a redelivered broker message cannot re-read a
token that was already handed to a worker). It implements the
:class:`WorkerBootstrapSecretSource` protocol so the bootstrap depends only
on the pure contract, not on this concrete registry.

Import purity: this module imports only the standard library, the pure
credential contract, the platform clock, and Pydantic's ``SecretStr``. No
FastAPI, SQLAlchemy, repositories, services, routers, Celery, or worker
runtime.
"""

from threading import Lock

from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialHandoff,
    WorkerCredentialResolution,
    WorkerCredentialResolutionOutcome,
)
from app.platform.clock import Clock

__all__ = ["InMemoryWorkerCredentialHandoffRegistry"]


class InMemoryWorkerCredentialHandoffRegistry:
    """Process-local, one-time store of worker credential handoffs.

    Implements :class:`WorkerBootstrapSecretSource`. Register a handoff at
    dispatch time (dev/test only); the worker bootstrap resolves it once by
    ``execution_id``. The raw token stays inside the stored
    :class:`WorkerCredentialHandoff`'s :class:`SecretStr`; this registry
    never unwraps it, so the token is never rendered, logged, or serialized
    here — the caller (the bootstrap) unwraps it exactly once when building
    the worker client.
    """

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._handoffs: dict[str, WorkerCredentialHandoff] = {}
        self._lock = Lock()

    def register(self, handoff: WorkerCredentialHandoff) -> None:
        """Store a handoff for later one-time resolution.

        Keyed by ``execution_id`` — the identifier the worker reliably holds
        from the validated envelope payload. Registering a second handoff
        for the same execution replaces the first (a re-issue supersedes the
        stale credential).
        """
        with self._lock:
            self._handoffs[handoff.execution_id] = handoff

    async def resolve(self, *, execution_id: str) -> WorkerCredentialResolution:
        """Resolve and consume the handoff for ``execution_id``.

        One-time: a successful resolution removes the handoff so a
        redelivered broker message cannot re-read the same token. An empty
        id is ``invalid_reference``; an unknown id is ``missing``; a handoff
        whose ``expires_at`` has passed is ``expired`` (and is dropped, so it
        cannot linger). Only ``found`` carries the raw token.
        """
        if not execution_id:
            return WorkerCredentialResolution(
                outcome=WorkerCredentialResolutionOutcome.invalid_reference
            )

        now = self._clock.now()
        with self._lock:
            handoff = self._handoffs.get(execution_id)
            if handoff is None:
                return WorkerCredentialResolution(
                    outcome=WorkerCredentialResolutionOutcome.missing
                )
            # Expiry is exclusive: a handoff at its expiry instant is dead.
            if now >= handoff.expires_at:
                # Drop the dead handoff so it cannot be resolved later.
                del self._handoffs[execution_id]
                return WorkerCredentialResolution(
                    outcome=WorkerCredentialResolutionOutcome.expired
                )
            # Consume: remove before returning so the token is handed out at
            # most once.
            del self._handoffs[execution_id]

        return WorkerCredentialResolution(
            outcome=WorkerCredentialResolutionOutcome.found,
            raw_token=handoff.raw_token,
            expires_at=handoff.expires_at,
        )

    def size(self) -> int:
        """Number of un-consumed handoffs (tests only)."""
        with self._lock:
            return len(self._handoffs)
