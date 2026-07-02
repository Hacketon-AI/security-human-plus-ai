"""The dispatch seam between the control plane and worker execution.

The API process must never run scanner logic. Instead it hands an immutable,
worker-bound :class:`WorkerDispatchPayload` to a :class:`ValidationDispatcher`.
The production dispatcher is intentionally fail-closed: no isolated worker
pipeline exists yet, so dispatch is refused rather than faked or run inline (see
``.claude/rules/security-boundaries.md`` and ``docs/stack-decision.md``).

Tests substitute a capturing dispatcher to assert the payload that *would* be
sent, without executing anything. This module imports no worker runtime
(``worker_runner`` / ``worker_process`` / transports), so the dispatch contract
can never become an execution path inside the API. The payload value object
lives in the FastAPI-free :mod:`dispatch_contracts` module and is re-exported
here for the dispatcher's callers.
"""

from typing import Protocol

from fastapi import Depends, Request

from app.config import Settings, ValidationDispatcherBackend
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.errors import ValidationDispatchNotConfigured
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialHandoff,
)
from app.platform.dependencies import get_app_settings

__all__ = [
    "UnconfiguredValidationDispatcher",
    "ValidationDispatcher",
    "WorkerDispatchPayload",
    "get_validation_dispatcher",
]


class ValidationDispatcher(Protocol):
    """Hands an immutable :class:`WorkerDispatchPayload` to the worker pipeline.

    Implementations must not execute scanner logic in the API process; they only
    enqueue/forward the frozen payload to an isolated executor.

    ``handoff`` is the per-execution worker credential side-channel (see
    :class:`WorkerCredentialHandoff`). It is passed as an *internal* argument
    so a dispatcher that provisions the worker out of band can read the raw
    token — it must **never** be placed on the broker message. A dispatcher
    that does not yet consume it (the broker publisher) simply ignores it and
    publishes only the credential-free envelope.
    """

    async def dispatch(
        self,
        payload: WorkerDispatchPayload,
        *,
        handoff: WorkerCredentialHandoff | None = None,
    ) -> None: ...


class UnconfiguredValidationDispatcher:
    """Fail-closed production dispatcher.

    Until the isolated worker pipeline is built, every dispatch is refused. This
    keeps the control plane honest: an execution can be queued and recorded, but
    nothing is ever run inline.
    """

    async def dispatch(
        self,
        payload: WorkerDispatchPayload,
        *,
        handoff: WorkerCredentialHandoff | None = None,
    ) -> None:
        raise ValidationDispatchNotConfigured(
            "validation dispatch is not configured for this environment"
        )


def get_validation_dispatcher(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> ValidationDispatcher:
    """FastAPI dependency returning the environment's dispatcher.

    Resolves the backend from settings: ``unconfigured`` (the production
    default) returns the fail-closed dispatcher, while the development-only
    ``in_memory`` backend returns the adapter bound to the app-state queue.
    The in-memory backend is already gated to development/test at startup by
    ``Settings._reject_in_memory_dispatcher_outside_development``; this seam
    fails closed if the queue was not provisioned (belt-and-suspenders).
    Tests override this dependency with a capturing fake.
    """
    backend = settings.validation_dispatcher_backend
    if backend is ValidationDispatcherBackend.in_memory:
        # Lazy import keeps ``dispatcher`` independent of the dev-only adapter at
        # module load time and avoids any transitive pull of the worker runtime
        # into the import graph of the production-wired dispatcher.
        from app.modules.validation_executions.in_memory_queue import (
            InMemoryValidationDispatcher,
        )

        queue = getattr(request.app.state, "validation_dispatch_queue", None)
        if queue is None:
            return UnconfiguredValidationDispatcher()
        return InMemoryValidationDispatcher(queue)
    if backend is ValidationDispatcherBackend.celery:
        # Lazy import for the same reason: keep the celery publisher out of the
        # dispatcher's load-time import graph. The publisher is bound to
        # ``app.state.validation_dispatch_publisher`` by a separate runtime wiring
        # step (not part of this skeleton). When the slot is empty, this seam
        # fails closed — selecting ``celery`` without a wired publisher rolls
        # the request transaction back rather than silently dropping the row.
        from app.modules.validation_executions.celery_publisher import (
            CeleryValidationDispatcher,
        )

        publisher = getattr(request.app.state, "validation_dispatch_publisher", None)
        if publisher is None:
            return UnconfiguredValidationDispatcher()
        return CeleryValidationDispatcher(publisher)
    return UnconfiguredValidationDispatcher()
