"""Development-only consumer for the in-memory validation dispatch queue.

A *worker-side* helper for development and tests: it dequeues one serialized
message at a time, drives the full worker lifecycle for it (worker-started →
runner → worker-finished), and reports a structured :class:`ConsumerResult`.
There is no loop, no thread, no scheduler, no retry — one call processes at
most one message. It exists only to prove the queue → worker → control-plane
lifecycle without standing up Celery/RabbitMQ; production execution still
goes through a real broker (deliberately not implemented yet).

This module is import-clean: it pulls in no FastAPI, no SQLAlchemy, no
application repositories/services/routers, no dispatcher, and no
``app.main``. The payload is read from the queue, never from the database or
an API fetch. The consumer is never wired into app startup or any request
handler — it cannot be enabled "automatically" by a production setting
because there is no setting that does that.

Delivery order is fixed: ``worker-started`` is posted *before* the runner is
allowed to run, and ``worker-finished`` is posted *after the runner returns*
— including when the runner raises. A runner exception is recovered into a
sanitized ``failed_safely`` :class:`WorkerFinishedRequest` so the execution
never lingers in ``executing`` (see ``.claude/rules/data-handling.md`` —
``error_message`` stays ``None`` and no payload, target, snapshot, evidence,
or token reaches the request).
"""

import logging
from dataclasses import dataclass
from enum import StrEnum

from app.modules.validation_executions.dispatch_serialization import (
    WorkerDispatchSerializationError,
    deserialize_worker_dispatch_payload,
    to_worker_input,
)
from app.modules.validation_executions.enums import ExecutionOutcome, StepStatus
from app.modules.validation_executions.executor import KillSwitch
from app.modules.validation_executions.in_memory_queue import InMemoryDispatchQueue
from app.modules.validation_executions.schemas import (
    WorkerFinishedRequest,
    WorkerStepResult,
)
from app.modules.validation_executions.worker_client import (
    WorkerClient,
    WorkerDeliveryResult,
)
from app.modules.validation_executions.worker_runner import (
    MalformedWorkerInput,
    TransportFactory,
    run_http_security_header_validation,
)

__all__ = [
    "ConsumerOutcome",
    "ConsumerResult",
    "consume_available",
    "consume_once",
]

_logger = logging.getLogger("securescope.validation.in_memory_consumer")

# Safe, static codes the consumer attaches to a recovery-built finished request.
# They are short, non-sensitive identifiers — never a raw exception type or
# message — and stay well within the ``WorkerFinishedRequest.error_code`` length.
_PAYLOAD_REJECTED_ERROR_CODE = "worker_payload_rejected"
_RUNTIME_FAILED_ERROR_CODE = "worker_runtime_failed"

# A generic, content-free summary that records that the run could not produce a
# verdict. It deliberately names nothing about the target, the payload, or the
# failure mode beyond what ``error_code`` already conveys.
_FAILED_SAFELY_SUMMARY = "worker run did not produce a result"


class ConsumerOutcome(StrEnum):
    """What happened to the consumed message.

    Outcomes are mutually exclusive and form the public surface of the dev
    consumer. They never carry payload content or sensitive detail. After a
    successful ``worker-started`` the consumer *always* posts a
    ``worker-finished``: a runner crash is recovered into a sanitized
    ``failed_safely`` request, so the only remaining terminal outcomes are
    ``delivered`` (the finished POST landed) and ``finished_delivery_failed``
    (it did not).
    """

    no_message = "no_message"
    malformed = "malformed"
    started_delivery_failed = "started_delivery_failed"
    finished_delivery_failed = "finished_delivery_failed"
    delivered = "delivered"


@dataclass(frozen=True, slots=True)
class ConsumerResult:
    """Structured outcome of one :func:`consume_once` call.

    ``message_id`` is the queue's opaque id for the consumed message, or
    ``None`` when the queue was empty. ``started_delivery`` is set once the
    consumer attempted the ``worker-started`` post (whether or not it
    succeeded); ``finished_delivery`` is set once the consumer attempted the
    ``worker-finished`` post (including the sanitized ``failed_safely`` post
    sent after a runner crash). Neither field is used to re-run the scan:
    the consumer is at-most-once.
    """

    message_id: str | None
    outcome: ConsumerOutcome
    started_delivery: WorkerDeliveryResult | None = None
    finished_delivery: WorkerDeliveryResult | None = None


def _build_failed_safely_request(error_code: str) -> WorkerFinishedRequest:
    """Build a sanitized ``failed_safely`` :class:`WorkerFinishedRequest`.

    Used to close out a consumer-driven run when the runner failed *after*
    ``worker-started`` succeeded — without this the execution would linger
    in ``executing``. The shape mirrors what
    :func:`result_mapping.to_worker_finished_request` would emit for a
    safe-stop result: ``succeeded=False``, ``outcome=failed_safely``, a
    short safe ``error_code``, ``error_message=None`` (no raw message ever
    crosses the wire — see ``.claude/rules/data-handling.md``), a generic
    content-free summary, and a single synthetic step. The executor is *not*
    called: the consumer can recover without re-entering scanner logic.
    """
    return WorkerFinishedRequest(
        succeeded=False,
        outcome=ExecutionOutcome.failed_safely,
        result_summary=_FAILED_SAFELY_SUMMARY,
        error_code=error_code,
        error_message=None,
        steps=[
            WorkerStepResult(
                step_name="worker",
                status=StepStatus.failed,
                evidence=None,
            )
        ],
    )


async def consume_once(
    queue: InMemoryDispatchQueue,
    client: WorkerClient,
    *,
    kill_switch: KillSwitch | None = None,
    transport_factory: TransportFactory | None = None,
) -> ConsumerResult:
    """Drive the full worker lifecycle for one queued message.

    The fixed sequence:

    1. **Dequeue.** Empty queue → :attr:`ConsumerOutcome.no_message` and no
       further work; never raises just because the queue is empty.
    2. **Deserialize.** Failure → :attr:`ConsumerOutcome.malformed`; *no*
       ``worker-started``, *no* target request, *no* ``worker-finished``.
    3. **Post ``worker-started``.** If it does not deliver (transport error
       or non-2xx), short-circuit with
       :attr:`ConsumerOutcome.started_delivery_failed`: the runner is *not*
       invoked and ``worker-finished`` is *not* posted, so no target request
       is made when the control plane is not ready for the transition.
    4. **Run the runner.** A runner exception is *recovered* into a
       sanitized ``failed_safely`` :class:`WorkerFinishedRequest`
       (:func:`_build_failed_safely_request`):
       :class:`MalformedWorkerInput` → ``worker_payload_rejected``; any
       other exception → ``worker_runtime_failed``. No raw exception is
       logged, returned, or sent as ``error_message``. This guarantees the
       execution does not stay in ``executing`` after the consumer returns.
    5. **Post ``worker-finished``.** Delivery success →
       :attr:`ConsumerOutcome.delivered`; delivery failure →
       :attr:`ConsumerOutcome.finished_delivery_failed`. There is no retry
       — re-running a scan to obtain a fresh result must be an operator
       decision, never an automatic loop.

    Logs carry only the opaque queue ``message_id`` and the coarse outcome
    — never the payload, target, evidence, snapshot, kill-switch token, or
    any credential.
    """
    item = queue.dequeue()
    if item is None:
        return ConsumerResult(message_id=None, outcome=ConsumerOutcome.no_message)

    try:
        payload = deserialize_worker_dispatch_payload(item.message)
        worker_input = to_worker_input(payload)
    except WorkerDispatchSerializationError:
        # Serialization errors carry no payload values (the contract enforces
        # this in dispatch_serialization), so they are safe to log.
        _logger.warning(
            "in-memory consumer rejected malformed message %s", item.message_id
        )
        return ConsumerResult(
            message_id=item.message_id, outcome=ConsumerOutcome.malformed
        )

    # Step 1: worker-started — gate the runner on this transition succeeding.
    try:
        started = await client.start(worker_input.execution_id)
    except Exception:
        # Auth-misconfigured / unexpected client error: surface a safe outcome
        # and never echo the raw exception (it could carry transport detail).
        _logger.warning(
            "in-memory consumer worker-started signal failed for message %s",
            item.message_id,
        )
        return ConsumerResult(
            message_id=item.message_id,
            outcome=ConsumerOutcome.started_delivery_failed,
        )
    if not started.delivered:
        _logger.warning(
            "in-memory consumer worker-started rejected for message %s",
            item.message_id,
        )
        return ConsumerResult(
            message_id=item.message_id,
            outcome=ConsumerOutcome.started_delivery_failed,
            started_delivery=started,
        )

    # Step 2: runner. A failure here is recovered into a sanitized
    # ``failed_safely`` request — never re-raised, never echoed — so the
    # execution is closed out instead of lingering in ``executing``.
    try:
        finished = await run_http_security_header_validation(
            worker_input,
            kill_switch=kill_switch,
            transport_factory=transport_factory,
        )
    except MalformedWorkerInput:
        _logger.warning(
            "in-memory consumer runner rejected payload for message %s; "
            "closing out as failed_safely",
            item.message_id,
        )
        finished = _build_failed_safely_request(_PAYLOAD_REJECTED_ERROR_CODE)
    except Exception:
        # Never echo a raw exception (could carry target/transport detail).
        _logger.warning(
            "in-memory consumer worker run failed for message %s; "
            "closing out as failed_safely",
            item.message_id,
        )
        finished = _build_failed_safely_request(_RUNTIME_FAILED_ERROR_CODE)

    # Step 3: worker-finished. The deliver call already swallows transport
    # errors into a safe ``WorkerDeliveryResult``; we still guard against
    # other failure modes (e.g. ``WorkerAuthNotConfigured``) and report them
    # as ``finished_delivery_failed`` without retrying.
    try:
        finished_delivery = await client.deliver(worker_input.execution_id, finished)
    except Exception:
        _logger.warning(
            "in-memory consumer worker-finished delivery failed for message %s",
            item.message_id,
        )
        return ConsumerResult(
            message_id=item.message_id,
            outcome=ConsumerOutcome.finished_delivery_failed,
            started_delivery=started,
        )

    outcome = (
        ConsumerOutcome.delivered
        if finished_delivery.delivered
        else ConsumerOutcome.finished_delivery_failed
    )
    _logger.info(
        "in-memory consumer processed message %s: %s",
        item.message_id,
        outcome.value,
    )
    return ConsumerResult(
        message_id=item.message_id,
        outcome=outcome,
        started_delivery=started,
        finished_delivery=finished_delivery,
    )


async def consume_available(
    queue: InMemoryDispatchQueue,
    client: WorkerClient,
    *,
    max_messages: int,
    kill_switch: KillSwitch | None = None,
    transport_factory: TransportFactory | None = None,
) -> list[ConsumerResult]:
    """Drain up to ``max_messages`` messages from the queue.

    Stops when the queue is empty or ``max_messages`` is reached — there is
    no loop guard, no retry, and no scheduling. ``max_messages`` must be
    positive; an unbounded drain is not a development convenience worth
    inviting. Failed messages are still counted toward the cap (the consumer
    never pulls extra messages to "make up" for a failure).
    """
    if max_messages < 1:
        raise ValueError("max_messages must be a positive integer")
    results: list[ConsumerResult] = []
    for _ in range(max_messages):
        result = await consume_once(
            queue,
            client,
            kill_switch=kill_switch,
            transport_factory=transport_factory,
        )
        if result.outcome is ConsumerOutcome.no_message:
            break
        results.append(result)
    return results
