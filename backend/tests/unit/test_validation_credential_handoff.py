"""Unit tests for the per-execution worker credential side-channel handoff.

Step 4A adds :class:`WorkerCredentialHandoff` — the in-memory carrier that
takes a freshly minted raw worker token from the dispatch path to a worker
bootstrap *out of band*. These tests pin the invariant the whole design rests
on: the raw token never crosses the broker boundary. Specifically it must not
appear in the serialized :class:`WorkerDispatchPayload`, the
:class:`ValidationDispatchEnvelope`, or an in-memory queue message, and it must
not be exposed by the handoff's own ``repr`` (it is a :class:`SecretStr`).

No DB, no FastAPI, no network: pure value-object and adapter behaviour.
"""

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.validation_executions.broker_contracts import (
    build_dispatch_envelope,
)
from app.modules.validation_executions.celery_publisher import envelope_to_dict
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatch_serialization import (
    serialize_worker_dispatch_payload,
)
from app.modules.validation_executions.in_memory_queue import (
    InMemoryDispatchQueue,
    InMemoryValidationDispatcher,
)
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialHandoff,
)
from pydantic import SecretStr

_RAW_TOKEN = "handoff-secret-raw-token-value-do-not-leak"
_EXECUTION_ID = "11111111-1111-1111-1111-111111111111"
_CREDENTIAL_ID = "22222222-2222-2222-2222-222222222222"


def _handoff() -> WorkerCredentialHandoff:
    return WorkerCredentialHandoff(
        execution_id=_EXECUTION_ID,
        credential_id=_CREDENTIAL_ID,
        raw_token=SecretStr(_RAW_TOKEN),
        expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
    )


def _payload() -> WorkerDispatchPayload:
    return WorkerDispatchPayload(
        execution_id=_EXECUTION_ID,
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        execution_specification={
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "target": "https://app.example.com/login",
            "kill_switch_token": "kill-switch-poll-key",
        },
        scope_snapshot={"allowed_ports": [443]},
        safety_snapshot={
            "timeout_seconds": 5.0,
            "redirect_limit": 3,
            "max_requests": 5,
            "max_response_bytes": 65536,
        },
    )


def test_handoff_carries_secretstr_and_hides_token_in_repr() -> None:
    handoff = _handoff()
    # The raw token is a SecretStr — its value never appears in repr.
    assert isinstance(handoff.raw_token, SecretStr)
    assert _RAW_TOKEN not in repr(handoff)
    assert _RAW_TOKEN not in str(handoff)
    # But it is retrievable exactly once for the worker bootstrap.
    assert handoff.raw_token.get_secret_value() == _RAW_TOKEN


def test_handoff_is_frozen() -> None:
    handoff = _handoff()
    with pytest.raises(dataclasses.FrozenInstanceError):
        handoff.raw_token = SecretStr("tampered")  # type: ignore[misc]


def test_raw_token_not_in_serialized_dispatch_payload() -> None:
    serialized = serialize_worker_dispatch_payload(_payload())
    assert _RAW_TOKEN not in str(serialized)
    # The payload has exactly the five contract fields — no credential field.
    assert set(serialized.keys()) == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }


def test_raw_token_not_in_dispatch_envelope() -> None:
    envelope = build_dispatch_envelope(
        _payload(),
        message_id="msg-1",
        created_at=datetime.now(tz=UTC).isoformat(),
        attempt=1,
    )
    envelope_dict = envelope_to_dict(envelope)
    assert _RAW_TOKEN not in str(envelope_dict)
    # The envelope carries no credential_id / raw_token field at all.
    assert "raw_token" not in envelope_dict
    assert "credential_id" not in envelope_dict
    assert _CREDENTIAL_ID not in str(envelope_dict)


async def test_in_memory_dispatch_ignores_handoff_and_keeps_queue_token_free() -> None:
    queue = InMemoryDispatchQueue()
    dispatcher = InMemoryValidationDispatcher(queue)

    # The handoff is passed as internal side-channel data; the dispatcher must
    # enqueue only the credential-free payload.
    await dispatcher.dispatch(_payload(), handoff=_handoff())

    item = queue.dequeue()
    assert item is not None
    assert _RAW_TOKEN not in str(item.message)
    assert _CREDENTIAL_ID not in str(item.message)
    assert "raw_token" not in item.message
    assert queue.size() == 0
