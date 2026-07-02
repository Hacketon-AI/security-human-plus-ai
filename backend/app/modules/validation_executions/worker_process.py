"""Local isolated-worker process entrypoint for ``HTTP_SECURITY_HEADER_VALIDATION``.

This is the worker-side orchestration a future queue consumer (or an operator
running it by hand) would call once it holds a frozen execution payload. It runs
the payload through the worker runner and delivers the sanitized result via an
injected :class:`WorkerClient` — nothing more.

It is deliberately *not* a daemon and *not* a queue consumer: :func:`run_once`
processes exactly one payload. It does no persistence, fetches no work from a
database or API, trusts no target outside the frozen payload, and imports no
session/repository/service/dispatcher/FastAPI machinery (scanner execution stays
isolated from the control plane — see ``.claude/rules/security-boundaries.md``).
There is no retry loop: a delivery failure is reported, never used as a reason to
re-run the scan.
"""

from dataclasses import dataclass

from app.modules.validation_executions.executor import KillSwitch
from app.modules.validation_executions.schemas import WorkerFinishedRequest
from app.modules.validation_executions.worker_client import (
    WorkerClient,
    WorkerDeliveryResult,
)
from app.modules.validation_executions.worker_runner import (
    TransportFactory,
    WorkerInput,
    run_http_security_header_validation,
)


class InactiveKillSwitch:
    """Default kill switch that never aborts.

    A real worker injects a switch that polls the control plane so a scan can be
    stopped mid-run. This default is only the safe stand-in for a single,
    manually invoked run; it never *enables* anything on its own.
    """

    async def is_active(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class RunOnceResult:
    """The product of one worker run: the result produced and its delivery.

    ``finished`` is the sanitized request the worker reported (or would report);
    ``delivery`` records whether the POST to the control plane succeeded.
    """

    finished: WorkerFinishedRequest
    delivery: WorkerDeliveryResult


async def run_once(
    worker_input: WorkerInput,
    client: WorkerClient,
    *,
    kill_switch: KillSwitch | None = None,
    transport_factory: TransportFactory | None = None,
) -> RunOnceResult:
    """Run one validation locally and deliver its result. One scan, one delivery.

    The runner validates the frozen payload first: a malformed payload raises
    (from the runner) before any target request *and* before any delivery, so a
    broken payload never produces a posted result. A run that stops safely
    (``failed_safely``) or is stopped by the kill switch (``blocked_by_control``)
    still yields a real result, which is delivered like any other. A delivery
    failure is captured in :class:`WorkerDeliveryResult`; the scan is never
    re-run to obtain a fresh result.

    ``transport_factory`` builds the target-scan transport and defaults to the
    runner's :class:`SafeHttpTransport`; it is injectable so the run is tested
    without real network I/O.
    """
    effective_kill_switch: KillSwitch = (
        kill_switch if kill_switch is not None else InactiveKillSwitch()
    )
    finished = await run_http_security_header_validation(
        worker_input,
        kill_switch=effective_kill_switch,
        transport_factory=transport_factory,
    )
    delivery = await client.deliver(worker_input.execution_id, finished)
    return RunOnceResult(finished=finished, delivery=delivery)
