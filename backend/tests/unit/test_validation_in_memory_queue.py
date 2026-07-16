"""Unit tests for the development-only in-memory dispatch queue.

These pin the safe behaviour of the dev/test adapter so it cannot drift into
being mistaken for a production orchestrator: JSON-safe storage, FIFO order,
import purity (no worker runtime / FastAPI / SQLAlchemy), startup rejection of
``in_memory`` outside development/test, and that the dispatcher only enqueues
— it never executes a worker.
"""

import ast
from dataclasses import is_dataclass
from typing import Any
from unittest.mock import patch

import pytest
from app.config import Environment, Settings, ValidationDispatcherBackend
from app.modules.validation_executions import in_memory_queue as in_memory_queue_module
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatch_serialization import (
    deserialize_worker_dispatch_payload,
)
from app.modules.validation_executions.dispatcher import (
    UnconfiguredValidationDispatcher,
)
from app.modules.validation_executions.errors import ValidationDispatchNotConfigured
from app.modules.validation_executions.in_memory_queue import (
    InMemoryDispatchQueue,
    InMemoryValidationDispatcher,
    QueuedDispatchMessage,
)
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION
from pydantic import SecretStr, ValidationError

_DSN = "postgresql+asyncpg://securescope:secret@localhost:5432/securescope"

_CONTRACT_FIELDS = frozenset(
    {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }
)


def _payload(
    execution_id: str = "11111111-1111-1111-1111-111111111111",
) -> WorkerDispatchPayload:
    return WorkerDispatchPayload(
        execution_id=execution_id,
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        execution_specification={
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "target": "https://app.example.com/login",
            "kill_switch_token": "opaque-poll-key",
        },
        scope_snapshot={"allowed_ports": [443]},
        safety_snapshot={
            "timeout_seconds": 5.0,
            "redirect_limit": 3,
            "max_requests": 5,
            "max_response_bytes": 65536,
            "kill_switch_active": False,
        },
    )


# --- Dispatcher: enqueue, FIFO, round-trip ---------------------------------


async def test_dispatcher_enqueues_one_serialized_payload() -> None:
    queue = InMemoryDispatchQueue()
    dispatcher = InMemoryValidationDispatcher(queue)

    await dispatcher.dispatch(_payload())

    assert queue.size() == 1
    item = queue.dequeue()
    assert item is not None
    assert isinstance(item, QueuedDispatchMessage)
    assert isinstance(item.message, dict)
    assert set(item.message.keys()) == _CONTRACT_FIELDS
    assert queue.size() == 0


async def test_payload_round_trips_through_serialize_deserialize() -> None:
    queue = InMemoryDispatchQueue()
    dispatcher = InMemoryValidationDispatcher(queue)
    original = _payload()

    await dispatcher.dispatch(original)

    item = queue.dequeue()
    assert item is not None
    restored = deserialize_worker_dispatch_payload(item.message)
    assert restored == original


async def test_fifo_ordering_is_preserved() -> None:
    queue = InMemoryDispatchQueue()
    dispatcher = InMemoryValidationDispatcher(queue)
    ids = [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    ]
    for execution_id in ids:
        await dispatcher.dispatch(_payload(execution_id=execution_id))

    drained: list[str] = []
    for _ in ids:
        item = queue.dequeue()
        assert item is not None
        drained.append(item.message["execution_id"])
    assert drained == ids
    assert queue.dequeue() is None


# --- Storage shape: JSON-safe, no dataclass/ORM/credentials ----------------


async def test_queue_stores_json_safe_dict_not_dataclass_or_orm() -> None:
    queue = InMemoryDispatchQueue()
    dispatcher = InMemoryValidationDispatcher(queue)

    await dispatcher.dispatch(_payload())

    item = queue.dequeue()
    assert item is not None
    assert type(item.message) is dict
    assert not is_dataclass(item.message)
    assert not isinstance(item.message, WorkerDispatchPayload)
    # Every value is a JSON primitive (no datetime/bytes/SecretStr/ORM).
    _assert_json_primitive(item.message)


def _assert_json_primitive(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            _assert_json_primitive(item)
    elif isinstance(value, list):
        for item in value:
            _assert_json_primitive(item)
    else:
        assert isinstance(value, str | int | float | type(None)), (
            f"non-JSON value of type {type(value).__name__} in queued message"
        )


async def test_no_evidence_tenant_or_credentials_in_queued_message() -> None:
    queue = InMemoryDispatchQueue()
    dispatcher = InMemoryValidationDispatcher(queue)

    await dispatcher.dispatch(_payload())

    item = queue.dequeue()
    assert item is not None
    message = item.message
    # The exact contract field set; nothing more, nothing less.
    assert set(message.keys()) == _CONTRACT_FIELDS
    # No tenant identity, request header, or user credential field anywhere
    # in the serialized message tree.
    forbidden_keys = {
        "organization_id",
        "tenant_id",
        "tenant",
        "x-organization-id",
        "X-Organization-Id",
        "x-worker-authorization",
        "X-Worker-Authorization",
        "authorization_header",
        "auth_token",
        "user",
        "user_id",
        "requested_by",
        "credential",
        "credentials",
        "secret",
        "evidence",
        "step_results",
    }
    _assert_keys_absent(message, forbidden_keys)


def _assert_keys_absent(value: object, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in forbidden, f"forbidden key {key!r} in queued message"
            _assert_keys_absent(item, forbidden)
    elif isinstance(value, list):
        for item in value:
            _assert_keys_absent(item, forbidden)


# --- The dispatcher does not run a worker ----------------------------------


async def test_dispatcher_does_not_execute_worker_runner_or_process() -> None:
    queue = InMemoryDispatchQueue()
    dispatcher = InMemoryValidationDispatcher(queue)

    # If the dispatcher accidentally invoked worker_runner.run_* or
    # worker_process.run_once, these patches would record it. The patches
    # target the source modules so any direct or transitive call is captured.
    from app.modules.validation_executions import worker_process, worker_runner

    with (
        patch.object(
            worker_runner,
            "run_http_security_header_validation",
            side_effect=AssertionError("worker_runner must not run in API"),
        ),
        patch.object(
            worker_process,
            "run_once",
            side_effect=AssertionError("worker_process must not run in API"),
        ),
    ):
        await dispatcher.dispatch(_payload())

    assert queue.size() == 1


# --- Dispatch failure leaves no queued item --------------------------------


async def test_dispatch_failure_does_not_leave_queued_item() -> None:
    queue = InMemoryDispatchQueue()
    dispatcher = InMemoryValidationDispatcher(queue)

    # Simulate a serialization-time failure: the queue must remain empty.
    with patch.object(
        in_memory_queue_module,
        "serialize_worker_dispatch_payload",
        side_effect=RuntimeError("forced serialization failure"),
    ):
        with pytest.raises(RuntimeError):
            await dispatcher.dispatch(_payload())

    assert queue.size() == 0
    assert queue.dequeue() is None


# --- Import purity ---------------------------------------------------------


_FORBIDDEN_IMPORT_TOKENS = (
    "worker_process",
    "worker_runner",
    "worker_client",
    "http_transport",
    "SafeHttpTransport",
    "HttpxTransportClient",
    "fastapi",
    "sqlalchemy",
    # SecureScope's persistence/router/service layers must not leak in either.
    "repository",
    "service",
    "router",
)


def _imported_modules(module: object) -> list[str]:
    source = module.__file__  # type: ignore[attr-defined]
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_in_memory_queue_module_does_not_import_worker_runtime() -> None:
    for module_name in _imported_modules(in_memory_queue_module):
        assert not any(token in module_name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"in_memory_queue.py must not import: {module_name}"
        )


# --- Settings gate: in_memory is rejected outside dev/test -----------------


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_in_memory_backend_rejected_outside_development(
    environment: Environment,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            environment=environment,
            database_dsn=SecretStr(_DSN),
            jwt_secret=SecretStr("test-only-deployed-jwt-secret"),
            worker_auth_token=SecretStr("deployed-token"),
            validation_dispatcher_backend=ValidationDispatcherBackend.in_memory,
            _env_file=None,
        )
    # The error names the rule but not any sensitive value.
    message = str(exc_info.value)
    assert "in_memory" in message
    assert "deployed-token" not in message


@pytest.mark.parametrize("environment", [Environment.development, Environment.test])
def test_in_memory_backend_allowed_in_development_and_test(
    environment: Environment,
) -> None:
    settings = Settings(
        environment=environment,
        database_dsn=SecretStr(_DSN),
        _env_file=None,
        validation_dispatcher_backend=ValidationDispatcherBackend.in_memory,
    )
    assert (
        settings.validation_dispatcher_backend is ValidationDispatcherBackend.in_memory
    )


@pytest.mark.parametrize(
    "environment",
    [
        Environment.development,
        Environment.test,
        Environment.staging,
        Environment.production,
    ],
)
def test_default_dispatcher_backend_is_unconfigured(environment: Environment) -> None:
    overrides: dict[str, Any] = {}
    if environment in (Environment.staging, Environment.production):
        overrides["jwt_secret"] = SecretStr("test-only-deployed-jwt-secret")
        overrides["worker_auth_token"] = SecretStr("deployed-token")
    settings = Settings(
        environment=environment,
        database_dsn=SecretStr(_DSN),
        _env_file=None,
        **overrides,
    )
    assert (
        settings.validation_dispatcher_backend
        is ValidationDispatcherBackend.unconfigured
    )


# --- Production-shape dispatcher remains fail-closed -----------------------


async def test_unconfigured_dispatcher_still_fails_closed() -> None:
    """The fail-closed dispatcher is unchanged by adding the dev adapter."""
    with pytest.raises(ValidationDispatchNotConfigured):
        await UnconfiguredValidationDispatcher().dispatch(_payload())
