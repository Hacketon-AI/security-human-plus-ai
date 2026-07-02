"""Development-only in-memory queue adapter for validation dispatch.

This is a safe, local adapter that proves the dispatch lifecycle —
``API create execution -> dispatcher serializes payload -> in-memory queue
stores a JSON-safe message`` — without any real broker. It is *not*
production orchestration. The production dispatcher in :mod:`dispatcher`
stays fail-closed until a real broker is wired (see
``.claude/rules/security-boundaries.md`` → scanner execution isolation and
``docs/stack-decision.md`` → worker boundary).

The queue and dispatcher live behind an explicit ``in_memory`` backend
setting that is rejected outside ``development``/``test`` at startup. The
queue stores only the JSON-safe dict produced by
:func:`serialize_worker_dispatch_payload`: never an ORM object, raw payload
object, evidence, tenant identity, request header, or user credential. No
worker is started, no scanner runs, and no HTTP transport is touched here.

Deliberate non-features (so the adapter cannot drift into being mistaken
for an orchestrator): no retry, no ack, no dead-letter, no scheduling, no
delivery hook. The adapter only enqueues; the dev-only consumer that drains
the queue lives outside the API process.

This module imports no worker runtime (``worker_process``, ``worker_runner``,
``worker_client``, ``http_transport``), no FastAPI, no SQLAlchemy
session/repository/service/router.
"""

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any
from uuid import uuid4

from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatch_serialization import (
    serialize_worker_dispatch_payload,
)
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialHandoff,
)

__all__ = [
    "InMemoryDispatchQueue",
    "InMemoryValidationDispatcher",
    "QueuedDispatchMessage",
]


@dataclass(frozen=True, slots=True)
class QueuedDispatchMessage:
    """A single FIFO queue entry: the message id and the JSON-safe payload.

    Mirrors the project's frozen value-object pattern so the dev consumer
    reads the payload by attribute name, not by tuple position. The
    ``message`` mapping is the output of
    :func:`serialize_worker_dispatch_payload` — already a plain ``dict`` of
    JSON primitives — so it is exposed without further copying.
    """

    message_id: str
    message: dict[str, Any]


class InMemoryDispatchQueue:
    """Process-local FIFO queue of JSON-safe dispatch messages.

    Items are stored as the plain ``dict`` produced by
    :func:`serialize_worker_dispatch_payload`. ORM rows, dataclasses,
    evidence, tenant headers, and user credentials are never stored. The
    lock makes concurrent ``enqueue``/``dequeue``/``size``/``clear`` safe;
    operations are short and non-blocking so a threading lock fits even
    though dispatch is called from ``async`` code.
    """

    def __init__(self) -> None:
        self._items: deque[QueuedDispatchMessage] = deque()
        self._lock = Lock()

    def enqueue(self, payload: WorkerDispatchPayload) -> str:
        """Serialize ``payload`` and append it to the queue.

        Returns the assigned message id. Serialization happens *before* the
        lock is taken so a serialization error never leaves a partially
        constructed item in the queue.
        """
        message = serialize_worker_dispatch_payload(payload)
        message_id = uuid4().hex
        with self._lock:
            self._items.append(
                QueuedDispatchMessage(message_id=message_id, message=message)
            )
        return message_id

    def dequeue(self) -> QueuedDispatchMessage | None:
        """Pop and return the oldest queued message, or ``None`` if empty.

        Returns the JSON-safe serialized form, never a
        :class:`WorkerDispatchPayload` instance or an ORM row. Reserved for
        the dev/test consumer of the in-memory adapter.
        """
        with self._lock:
            if not self._items:
                return None
            return self._items.popleft()

    def size(self) -> int:
        """Return the current number of queued messages (for tests)."""
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        """Drop every queued message (for tests)."""
        with self._lock:
            self._items.clear()


class InMemoryValidationDispatcher:
    """Dispatcher that enqueues a JSON-safe dispatch message in process memory.

    Implements the ``ValidationDispatcher`` protocol from :mod:`dispatcher`.
    It never starts a worker, never invokes ``worker_process``/``worker_runner``,
    and never touches an HTTP transport — it only serializes and enqueues. It
    returns once the queue has accepted the message; a serialization or queue
    error propagates so the caller's request transaction rolls back without
    leaving an orphan queued item.
    """

    def __init__(self, queue: InMemoryDispatchQueue) -> None:
        self._queue = queue

    async def dispatch(
        self,
        payload: WorkerDispatchPayload,
        *,
        handoff: WorkerCredentialHandoff | None = None,
    ) -> None:
        # The credential handoff is intentionally ignored by the dev adapter:
        # the raw token must never enter a queue message (see
        # docs/validation-worker-credentials-design.md → broker envelope rule).
        # Only the JSON-safe, credential-free payload is enqueued. A real
        # worker bootstrap consuming the handoff is a later production step.
        self._queue.enqueue(payload)
