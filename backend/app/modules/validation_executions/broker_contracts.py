"""Production broker contract for validation execution dispatch.

The control plane hands a frozen :class:`WorkerDispatchPayload` to a
publisher; a future broker (Celery on RabbitMQ in our stack — see
``docs/stack-decision.md``) carries it to a worker process that runs the
scan in isolation. *This module defines the contract only*: the wire
envelope, the publisher and consumer protocols, and the validation that
keeps unsafe values (datetime, bytes, ``SecretStr``, ORM rows, evidence,
tenant headers, credentials) out of the wire format. No real broker is
implemented here — production dispatch stays fail-closed in
:mod:`dispatcher` until a concrete publisher is wired (see
``docs/validation-dispatch-broker-design.md`` for the rollout plan).

The module is deliberately import-clean: it pulls in no FastAPI, no
SQLAlchemy, no application repositories/services/routers, no
``worker_runner``, ``worker_process``, ``worker_client``, or
``http_transport`` — only the standard library and the FastAPI-free
:mod:`dispatch_contracts` / :mod:`dispatch_serialization` modules. This
makes the contract safe to share between the API package and a future
worker package without dragging either side's runtime into the other.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatch_serialization import (
    serialize_worker_dispatch_payload,
)

__all__ = [
    "DISPATCH_CONTENT_TYPE",
    "DISPATCH_ENVELOPE_SCHEMA_VERSION",
    "BrokerConsumerOutcome",
    "BrokerConsumerResult",
    "BrokerEnvelopeError",
    "DispatchPublishOutcome",
    "DispatchPublishResult",
    "ValidationDispatchConsumer",
    "ValidationDispatchEnvelope",
    "ValidationDispatchPublisher",
    "build_dispatch_envelope",
    "canonical_payload_sha256",
]

# Current on-wire schema version. Bump when the envelope shape changes —
# consumers refuse to process an envelope whose schema_version they do not
# understand, so this is the producer's promise to consumers.
DISPATCH_ENVELOPE_SCHEMA_VERSION = "1"

# Wire content type. The envelope only ever carries JSON-safe payloads, and
# the broker (RabbitMQ) is configured to mark them as such — see the
# design doc. Any other content type at the contract boundary is rejected.
DISPATCH_CONTENT_TYPE = "application/json"

# The exact ordered field set of a serialized ``WorkerDispatchPayload``.
# Mirrors ``dispatch_serialization._FIELDS`` (and ``WorkerDispatchPayload``
# itself) — duplicated here so this module stays the single source of truth
# for the envelope contract without importing serialization internals.
_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }
)


class BrokerEnvelopeError(Exception):
    """An envelope failed the broker contract.

    Messages name the violated rule using only the contract's fixed
    vocabulary — never the offending payload value or a caller-supplied key
    — so a malformed or hostile message cannot leak its contents.
    """


@dataclass(frozen=True, slots=True)
class ValidationDispatchEnvelope:
    """The wire envelope carrying a frozen ``WorkerDispatchPayload``.

    The envelope is the broker's view of a dispatch. ``payload`` is the
    JSON-safe :class:`WorkerDispatchPayload` (already serialized by
    :func:`serialize_worker_dispatch_payload`) — never an ORM row, never an
    enum object, never bytes/``SecretStr``/datetime, never evidence, never
    tenant headers, and never a worker credential. ``payload_sha256`` lets
    the consumer detect tampering or accidental drift over the wire.
    ``attempt`` is the broker's *delivery* attempt count, not an API retry:
    the API never re-publishes the same execution; the broker may redeliver
    if a worker fails to ack.

    Construction validates the contract; any violation raises
    :class:`BrokerEnvelopeError` with a content-free message.
    """

    message_id: str
    schema_version: str
    payload: Mapping[str, Any]
    payload_sha256: str
    created_at: str
    attempt: int
    content_type: str = DISPATCH_CONTENT_TYPE
    trace_id: str | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        _validate_envelope(self)


class DispatchPublishOutcome(StrEnum):
    """What happened to a single ``publish`` call.

    ``published`` — the broker accepted the message. ``rejected`` — the
    broker refused (e.g. invalid envelope, queue not configured).
    ``publish_failed`` — a transport error reached the publisher. The
    publisher never retries automatically: re-publishing is an operator
    decision and an execution must never run twice for the same message
    without idempotency support (see the design doc → retry boundaries).
    """

    published = "published"
    rejected = "rejected"
    publish_failed = "publish_failed"


@dataclass(frozen=True, slots=True)
class DispatchPublishResult:
    """Structured outcome of one publish attempt.

    ``message_id`` is set when the broker assigned an id; ``failure`` is a
    coarse, non-sensitive category (e.g. ``"transport_error"``) and is set
    only when ``outcome`` is not :attr:`DispatchPublishOutcome.published`.
    Never carries a raw broker/network exception.
    """

    outcome: DispatchPublishOutcome
    message_id: str | None = None
    failure: str | None = None


class BrokerConsumerOutcome(StrEnum):
    """What a broker-side consumer did with one message.

    Parallel to ``in_memory_consumer.ConsumerOutcome`` but defined here so
    a production consumer can satisfy the broker contract without taking a
    dependency on the dev-only adapter. A concrete consumer is responsible
    for ack/nack with the broker; this enum is the *result* of one
    ``consume_once`` call, not a broker transport status.
    """

    no_message = "no_message"
    malformed = "malformed"
    started_delivery_failed = "started_delivery_failed"
    finished_delivery_failed = "finished_delivery_failed"
    delivered = "delivered"


@dataclass(frozen=True, slots=True)
class BrokerConsumerResult:
    """Structured outcome of one broker-consumer ``consume_once`` call.

    Minimal on purpose: the production consumer reports only the broker
    message id and a coarse outcome. Delivery details for the worker hooks
    (started/finished) belong to the consumer's logs and tracing, not to a
    public result type that any caller could persist.
    """

    message_id: str | None
    outcome: BrokerConsumerOutcome


class ValidationDispatchPublisher(Protocol):
    """Publishes a frozen ``WorkerDispatchPayload`` onto a broker.

    Implementations build a :class:`ValidationDispatchEnvelope` from the
    payload (via :func:`build_dispatch_envelope`), commit it to the broker,
    and return a typed :class:`DispatchPublishResult`. Implementations must
    not call the worker runtime (``worker_runner`` / ``worker_process``),
    must not call the worker HTTP client, and must not run any scanner
    logic in-process — see ``.claude/rules/security-boundaries.md``
    (scanner execution isolation).
    """

    async def publish(
        self, payload: WorkerDispatchPayload
    ) -> DispatchPublishResult: ...


class ValidationDispatchConsumer(Protocol):
    """Worker-side broker consumer for queued envelopes.

    A concrete consumer dequeues one envelope from the broker, validates
    its envelope/payload contract, drives the worker lifecycle through the
    existing worker hooks, and returns a :class:`BrokerConsumerResult`. The
    consumer runs *outside* the API process and is never wired into app
    startup or any request handler. No real consumer is implemented in this
    module — it exists only to fix the worker-side contract for a future
    Celery worker (see the design doc → rollout plan).
    """

    async def consume_once(self) -> BrokerConsumerResult: ...


def canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    """Return the SHA-256 of the canonical JSON encoding of ``payload``.

    Stable across runs and processes: keys are sorted, separators are the
    minimal ``(',', ':')`` form, and Unicode passes through unchanged. This
    is the *contract* hash a consumer recomputes from the on-wire payload
    to detect tampering or accidental drift; it is also what the envelope
    stores in ``payload_sha256``.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_dispatch_envelope(
    payload: WorkerDispatchPayload,
    *,
    message_id: str,
    created_at: str,
    attempt: int = 1,
    trace_id: str | None = None,
    idempotency_key: str | None = None,
) -> ValidationDispatchEnvelope:
    """Wrap a frozen ``WorkerDispatchPayload`` in a wire envelope.

    Serializes the payload through :func:`serialize_worker_dispatch_payload`
    (so only contract fields with JSON-safe values pass through), computes
    the canonical SHA-256, and constructs the envelope. ``message_id``,
    ``created_at`` (ISO-8601 UTC), and ``attempt`` are caller-supplied so
    the producer owns id assignment and the wall clock — keeping this
    factory deterministic and import-pure.
    """
    serialized = serialize_worker_dispatch_payload(payload)
    return ValidationDispatchEnvelope(
        message_id=message_id,
        schema_version=DISPATCH_ENVELOPE_SCHEMA_VERSION,
        payload=serialized,
        payload_sha256=canonical_payload_sha256(serialized),
        created_at=created_at,
        attempt=attempt,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
    )


def _validate_envelope(envelope: ValidationDispatchEnvelope) -> None:
    """Reject any envelope that does not satisfy the broker contract.

    The checks intentionally name only the contract's fixed vocabulary so
    a malformed envelope cannot leak its values through an error message.
    """
    if not envelope.message_id:
        raise BrokerEnvelopeError("message_id must be a non-empty string")
    if not envelope.schema_version:
        raise BrokerEnvelopeError("schema_version must be a non-empty string")
    if not envelope.created_at:
        raise BrokerEnvelopeError("created_at must be a non-empty string")
    if envelope.content_type != DISPATCH_CONTENT_TYPE:
        raise BrokerEnvelopeError(f"content_type must be {DISPATCH_CONTENT_TYPE!r}")
    if envelope.attempt < 1:
        raise BrokerEnvelopeError("attempt must be a positive integer")
    if not isinstance(envelope.payload, Mapping):
        raise BrokerEnvelopeError("payload must be a mapping of contract fields")
    if set(envelope.payload.keys()) != _PAYLOAD_FIELDS:
        raise BrokerEnvelopeError("payload must contain exactly the contract fields")
    _assert_json_safe(envelope.payload)
    if envelope.payload_sha256 != canonical_payload_sha256(envelope.payload):
        raise BrokerEnvelopeError("payload_sha256 does not match payload")


def _assert_json_safe(value: object) -> None:
    """Recursively assert ``value`` contains only JSON primitives.

    Allowed: ``str`` (incl. bool/int/float/None), ``list``/``tuple`` of
    JSON values, and ``dict`` with string keys. Anything else — datetime,
    bytes, ``SecretStr``, enum object, dataclass, ORM row — is rejected
    with a content-free :class:`BrokerEnvelopeError` so payload values are
    never echoed in the error message.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise BrokerEnvelopeError("payload dict keys must be strings")
            _assert_json_safe(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_json_safe(item)
        return
    # ``bool`` is a subclass of ``int`` — both are allowed.
    if isinstance(value, str | int | float | type(None)):
        return
    raise BrokerEnvelopeError(
        f"payload contains a non-JSON-safe value of type {type(value).__name__}"
    )
