"""Celery/RabbitMQ publisher skeleton for validation dispatch.

This is the publisher side only. It builds a
:class:`ValidationDispatchEnvelope` from the frozen
:class:`WorkerDispatchPayload`, hands a JSON-safe dict to an injected sender,
and reports a typed :class:`DispatchPublishResult`. The worker consumer is
**not** implemented here — see ``docs/validation-dispatch-broker-design.md``
→ rollout plan.

The module is deliberately import-clean: it pulls in no FastAPI, no
SQLAlchemy, no application repositories/services/routers, no worker runtime
(``worker_runner`` / ``worker_process`` / ``worker_client`` /
``http_transport``), and — importantly — no ``celery``. A real Celery sender
lives behind the :class:`CelerySendTask` Protocol and is provided by a
separate runtime wiring module (out of scope for this skeleton). Tests inject
a fake sender, so a live RabbitMQ is never required to exercise the
publisher's logic.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from app.modules.validation_executions.broker_contracts import (
    BrokerEnvelopeError,
    DispatchPublishOutcome,
    DispatchPublishResult,
    ValidationDispatchEnvelope,
    build_dispatch_envelope,
)
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.errors import ValidationDispatchNotConfigured
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialHandoff,
)
from app.platform.clock import Clock

__all__ = [
    "CeleryDispatchSettings",
    "CelerySendError",
    "CelerySendTask",
    "CeleryValidationDispatchPublisher",
    "CeleryValidationDispatcher",
    "envelope_to_dict",
]

_logger = logging.getLogger("securescope.validation.celery_publisher")


class CelerySendError(Exception):
    """A publish attempt failed to reach the broker.

    Carries no broker URL, no envelope content, and no exception detail —
    messages stay inside the contract vocabulary so a broker error cannot
    leak the URL, credentials, payload, or any target the producer is aware
    of. Raised by sender implementations; the publisher catches it and maps
    to :class:`DispatchPublishOutcome.publish_failed`.
    """


@dataclass(frozen=True, slots=True)
class CeleryDispatchSettings:
    """Static broker addressing for the validation dispatch task.

    Plain strings only — the broker URL is *not* held here, because the
    publisher does not need to know it (the sender does). Keeping these
    fields plain prevents the publisher from ever logging a credential by
    accident.
    """

    task_name: str
    routing_key: str
    queue_name: str
    exchange: str
    schema_version: str


class CelerySendTask(Protocol):
    """Sends one Celery task message. Injected so tests don't need a broker.

    Implementations call Celery's ``send_task`` (or an equivalent
    broker-side primitive) with ``ignore_result=True``: there is no Celery
    result backend in this design — the worker reports back via the
    existing ``worker-finished`` hook. Implementations must not retry; the
    publisher does not retry either. A transport failure is raised as
    :class:`CelerySendError` so the publisher can map it to a safe outcome
    without seeing broker internals.
    """

    def __call__(
        self,
        *,
        task_name: str,
        kwargs: Mapping[str, Any],
        routing_key: str,
        queue: str,
        exchange: str,
        ignore_result: bool,
    ) -> str: ...


def envelope_to_dict(envelope: ValidationDispatchEnvelope) -> dict[str, Any]:
    """Render the envelope as a plain JSON-safe dict for the sender.

    The result mirrors the envelope's contract fields exactly. The payload
    mapping is shallow-copied into a plain ``dict`` so the sender receives
    a true ``dict`` (some brokers require it). No envelope contents are
    reformatted: ``build_dispatch_envelope`` already enforced JSON safety,
    and this function does not reinterpret values.
    """
    return {
        "message_id": envelope.message_id,
        "schema_version": envelope.schema_version,
        "payload": dict(envelope.payload),
        "payload_sha256": envelope.payload_sha256,
        "created_at": envelope.created_at,
        "attempt": envelope.attempt,
        "content_type": envelope.content_type,
        "trace_id": envelope.trace_id,
        "idempotency_key": envelope.idempotency_key,
    }


class CeleryValidationDispatchPublisher:
    """Publishes a frozen :class:`WorkerDispatchPayload` as a Celery task message.

    Implements :class:`ValidationDispatchPublisher`. Builds the envelope
    via :func:`build_dispatch_envelope` (which enforces the JSON-safe
    contract — no datetime, no bytes, no ORM rows, no evidence, no
    credentials), serializes it to a plain dict, and hands the dict to the
    injected sender with ``ignore_result=True``. The publisher never
    executes scanner logic, never waits for a Celery result, and never
    retries on failure — re-publishing is an operator decision.
    """

    def __init__(
        self,
        sender: CelerySendTask,
        settings: CeleryDispatchSettings,
        clock: Clock,
    ) -> None:
        self._sender = sender
        self._settings = settings
        self._clock = clock

    async def publish(self, payload: WorkerDispatchPayload) -> DispatchPublishResult:
        """Build an envelope, hand it to the sender, and report the outcome.

        Envelope construction failures (a payload field that is not
        JSON-safe, a missing contract field, etc.) become
        :attr:`DispatchPublishOutcome.rejected` with a content-free
        failure code. Broker transport failures become
        :attr:`DispatchPublishOutcome.publish_failed`. Success returns the
        broker-assigned task id as ``message_id``. Logs name only the
        opaque execution id and the coarse outcome — never the envelope
        body, the broker URL, the task id payload, or any credential.
        """
        try:
            envelope = build_dispatch_envelope(
                payload,
                message_id=uuid4().hex,
                created_at=self._clock.now().isoformat(),
                attempt=1,
            )
        except BrokerEnvelopeError:
            _logger.warning(
                "celery publisher rejected envelope for execution %s",
                payload.execution_id,
            )
            return DispatchPublishResult(
                outcome=DispatchPublishOutcome.rejected,
                failure="envelope_rejected",
            )

        if envelope.schema_version != self._settings.schema_version:
            # The producer and the static settings disagree on the wire
            # contract. Surface this as a rejection rather than publishing a
            # message a consumer cannot interpret.
            _logger.warning(
                "celery publisher rejected envelope for execution %s "
                "due to schema_version mismatch",
                payload.execution_id,
            )
            return DispatchPublishResult(
                outcome=DispatchPublishOutcome.rejected,
                failure="schema_version_mismatch",
            )

        envelope_dict = envelope_to_dict(envelope)
        try:
            task_id = self._sender(
                task_name=self._settings.task_name,
                kwargs={"envelope": envelope_dict},
                routing_key=self._settings.routing_key,
                queue=self._settings.queue_name,
                exchange=self._settings.exchange,
                ignore_result=True,
            )
        except CelerySendError:
            _logger.warning(
                "celery publish failed for execution %s", payload.execution_id
            )
            return DispatchPublishResult(
                outcome=DispatchPublishOutcome.publish_failed,
                failure="broker_send_failed",
            )
        except Exception:
            # Never echo a raw exception — it could carry the broker URL or
            # credentials embedded in it.
            _logger.warning(
                "celery publish unexpected failure for execution %s",
                payload.execution_id,
            )
            return DispatchPublishResult(
                outcome=DispatchPublishOutcome.publish_failed,
                failure="broker_send_failed",
            )

        _logger.info("celery publish succeeded for execution %s", payload.execution_id)
        return DispatchPublishResult(
            outcome=DispatchPublishOutcome.published,
            message_id=task_id,
        )


class CeleryValidationDispatcher:
    """:class:`ValidationDispatcher` that publishes via Celery.

    Thin adapter so ``service.dispatch_queued`` can use the seam without
    knowing about the broker. The Protocol's ``dispatch`` returns ``None``,
    so a non-``published`` outcome is surfaced as
    :class:`ValidationDispatchNotConfigured` — exactly the contract the
    fail-closed dispatcher uses. The service's call sits inside the request
    transaction, so a raised failure rolls back the queued row: nothing is
    left in the database that was not handed to the broker.
    """

    def __init__(self, publisher: CeleryValidationDispatchPublisher) -> None:
        self._publisher = publisher

    async def dispatch(
        self,
        payload: WorkerDispatchPayload,
        *,
        handoff: WorkerCredentialHandoff | None = None,
    ) -> None:
        # The credential handoff is deliberately *not* consumed here: the
        # broker envelope must stay credential-free (no raw token, no
        # credential_id) — see docs/validation-dispatch-broker-design.md.
        # Only the JSON-safe envelope is published. Wiring the handoff to a
        # real worker bootstrap (container secret / out-of-band fetch) is the
        # next production step; until then the publisher ignores it.
        result = await self._publisher.publish(payload)
        if result.outcome is not DispatchPublishOutcome.published:
            raise ValidationDispatchNotConfigured(
                "validation dispatch publisher did not publish"
            )
