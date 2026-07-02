"""Worker-side bootstrap: inject the per-execution credential at run time.

The Celery worker consumer (:mod:`celery_worker`) needs a
:class:`WorkerClient` carrying *this execution's* raw credential to drive
the ``worker-started`` / ``worker-finished`` hooks. That credential must
**not** travel in the broker envelope — the envelope stays credential-free
(see ``docs/validation-worker-credentials-design.md`` → Step 4B). This
module is the boundary that closes the gap: it reads the (validated)
execution id from the envelope, resolves the raw token from a side-channel
:class:`WorkerBootstrapSecretSource`, builds the worker client, and hands
off to the tested :func:`run_validation_envelope`.

Failure is fail-closed: a malformed envelope, a missing/expired/invalid
side-channel credential, or an unavailable source all short-circuit
*before* ``worker-started`` — the scan never runs and no target request is
made. The optional shared-token fallback is **off** unless a caller passes
an explicit transitional token, mirroring the server-side
``worker_shared_token_fallback_enabled`` gate.

Import purity: this module imports the worker consumer, the worker client,
the pure credential contract, and (for the Celery wrapper) ``celery`` under
``TYPE_CHECKING`` only. It imports no FastAPI, no SQLAlchemy, no
repositories, no services, no routers, and never ``app.main``.
"""

import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr

from app.modules.validation_executions.broker_contracts import (
    BrokerConsumerOutcome,
    BrokerConsumerResult,
)
from app.modules.validation_executions.celery_worker import (
    DEFAULT_VALIDATION_TASK_NAME,
    envelope_execution_id,
    run_validation_envelope,
)
from app.modules.validation_executions.executor import KillSwitch
from app.modules.validation_executions.worker_client import WorkerClient
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerBootstrapSecretSource,
    WorkerCredentialResolutionOutcome,
)
from app.modules.validation_executions.worker_runner import TransportFactory

if TYPE_CHECKING:
    # Type-only import so the bootstrap core is importable without ``celery``
    # present. Only the task-registration wrapper needs the real package.
    from celery import Celery

__all__ = [
    "WorkerClientFactory",
    "build_run_validation_task_with_handoff_source",
    "run_validation_envelope_with_handoff",
]

_logger = logging.getLogger("securescope.validation.celery_worker_bootstrap")

# Builds a control-plane worker client from a resolved raw token. Injected so
# the bootstrap never constructs an HTTP transport itself — tests pass a
# fake-transport-backed client, production passes a factory that wraps a real
# ``WorkerResultTransport``.
WorkerClientFactory = Callable[[SecretStr], WorkerClient]


async def run_validation_envelope_with_handoff(
    envelope: Mapping[str, Any],
    *,
    source: WorkerBootstrapSecretSource,
    client_factory: WorkerClientFactory,
    kill_switch: KillSwitch | None = None,
    transport_factory: TransportFactory | None = None,
    shared_token_fallback: SecretStr | None = None,
) -> BrokerConsumerResult:
    """Resolve the side-channel credential and run one envelope.

    The fixed sequence:

    1. **Validate the envelope enough to read the execution id.** A
       malformed envelope resolves to
       :attr:`BrokerConsumerOutcome.malformed` — no credential lookup, no
       ``worker-started``, no target request.
    2. **Resolve the raw token from the side-channel** keyed by execution
       id. Only :attr:`WorkerCredentialResolutionOutcome.found` yields a
       token. ``missing`` / ``expired`` / ``invalid_reference`` /
       ``source_unavailable`` fail closed with
       :attr:`BrokerConsumerOutcome.started_delivery_failed` — the worker
       never authenticates, so nothing runs. If an explicit
       ``shared_token_fallback`` token was supplied *and* the source did
       not return a token, the fallback token is used instead (transitional
       only; default is no fallback).
    3. **Build the worker client** from the resolved token via
       ``client_factory`` and delegate to the tested
       :func:`run_validation_envelope`, which performs the
       started → runner → finished lifecycle.

    The raw token is never logged, never serialized, and lives only inside
    the ``SecretStr`` until ``client_factory`` unwraps it. Logs carry only
    the execution id (a non-sensitive identifier) and a coarse outcome.
    """
    execution_id = envelope_execution_id(envelope)
    if execution_id is None:
        _logger.warning("worker bootstrap rejected malformed envelope")
        return BrokerConsumerResult(
            message_id=None, outcome=BrokerConsumerOutcome.malformed
        )

    resolution = await source.resolve(execution_id=execution_id)
    raw_token = resolution.raw_token
    if resolution.outcome is not WorkerCredentialResolutionOutcome.found:
        if shared_token_fallback is not None:
            # Transitional: the operator explicitly opted into the shared
            # token on the worker side. The server still rejects it unless
            # its own fallback flag is on, so this cannot silently widen
            # authority.
            _logger.warning(
                "worker bootstrap using transitional shared-token fallback "
                "for execution %s (side-channel outcome: %s)",
                execution_id,
                resolution.outcome.value,
            )
            raw_token = shared_token_fallback
        else:
            _logger.warning(
                "worker bootstrap could not resolve credential for execution "
                "%s (outcome: %s); failing closed before worker-started",
                execution_id,
                resolution.outcome.value,
            )
            return BrokerConsumerResult(
                message_id=None,
                outcome=BrokerConsumerOutcome.started_delivery_failed,
            )

    # ``found`` with a null token would be a contract violation upstream;
    # guard defensively so a bad source can never build an unauthenticated
    # client.
    if raw_token is None:
        _logger.warning(
            "worker bootstrap resolution reported found but carried no token "
            "for execution %s; failing closed",
            execution_id,
        )
        return BrokerConsumerResult(
            message_id=None,
            outcome=BrokerConsumerOutcome.started_delivery_failed,
        )

    client = client_factory(raw_token)
    return await run_validation_envelope(
        envelope,
        client,
        kill_switch=kill_switch,
        transport_factory=transport_factory,
    )


def build_run_validation_task_with_handoff_source(
    celery_app: "Celery",
    *,
    source: WorkerBootstrapSecretSource,
    client_factory: WorkerClientFactory,
    kill_switch: KillSwitch,
    transport_factory: TransportFactory | None = None,
    shared_token_fallback: SecretStr | None = None,
    task_name: str = DEFAULT_VALIDATION_TASK_NAME,
) -> Any:
    """Register a Celery task that resolves the credential via the side-channel.

    Thin wrapper over :func:`run_validation_envelope_with_handoff`: the task
    body is a single ``asyncio.run`` call, ``ignore_result=True`` (no result
    backend — the worker reports via the ``worker-finished`` hook), and no
    retry is configured (the broker driver decides ack/requeue). The
    ``source`` (side-channel), ``client_factory`` (client builder),
    ``kill_switch``, and optional ``transport_factory`` /
    ``shared_token_fallback`` are injected by the operational worker
    bootstrap; they are not constructed here, and this module is never bound
    to ``app.main`` or imported by the dispatcher/service/router.
    """

    @celery_app.task(name=task_name, ignore_result=True)  # type: ignore[untyped-decorator]
    def run_validation(envelope: Mapping[str, Any]) -> None:
        asyncio.run(
            run_validation_envelope_with_handoff(
                envelope,
                source=source,
                client_factory=client_factory,
                kill_switch=kill_switch,
                transport_factory=transport_factory,
                shared_token_fallback=shared_token_fallback,
            )
        )

    return run_validation
