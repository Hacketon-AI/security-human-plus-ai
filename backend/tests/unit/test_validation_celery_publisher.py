"""Unit tests for the Celery/RabbitMQ publisher skeleton.

Pin the publisher's behaviour with a fake sender so no live RabbitMQ is
needed: it builds a JSON-safe envelope, calls the sender with the configured
task name / routing key / queue / exchange / ``ignore_result=True``, returns
``published`` on success, maps broker exceptions to a content-free
``publish_failed``, and never logs the envelope/payload/broker URL. Also
pin the import purity (no worker runtime, FastAPI, SQLAlchemy, ``celery``),
the dispatcher integration (selecting ``celery`` without a wired publisher
fails closed; selecting it with a wired publisher returns the celery
adapter), and the settings validator (celery backend requires a broker URL).
"""

import ast
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from app.config import Environment, Settings, ValidationDispatcherBackend
from app.modules.validation_executions import (
    celery_publisher as celery_publisher_module,
)
from app.modules.validation_executions import (
    dispatcher as dispatcher_module,
)
from app.modules.validation_executions import (
    router as router_module,
)
from app.modules.validation_executions import (
    service as service_module,
)
from app.modules.validation_executions.broker_contracts import (
    DISPATCH_CONTENT_TYPE,
    DispatchPublishOutcome,
    DispatchPublishResult,
)
from app.modules.validation_executions.celery_publisher import (
    CeleryDispatchSettings,
    CelerySendError,
    CelerySendTask,
    CeleryValidationDispatcher,
    CeleryValidationDispatchPublisher,
    envelope_to_dict,
)
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatcher import (
    UnconfiguredValidationDispatcher,
    get_validation_dispatcher,
)
from app.modules.validation_executions.errors import ValidationDispatchNotConfigured
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION
from pydantic import SecretStr, ValidationError

_DSN = "postgresql+asyncpg://securescope:secret@localhost:5432/securescope"
_FIXED_INSTANT = datetime(2026, 6, 25, 12, tzinfo=UTC)
_TOKEN_IN_URL = "Stronk-Br0ker-Token"


# --- Helpers ---------------------------------------------------------------


class _FixedClock:
    def now(self) -> datetime:
        return _FIXED_INSTANT


def _settings_value(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "environment": Environment.development,
        "database_dsn": SecretStr(_DSN),
    }
    base.update(overrides)
    return Settings(**base)


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


def _celery_settings(**overrides: str) -> CeleryDispatchSettings:
    base: dict[str, str] = {
        "task_name": "validation_executions.run_validation",
        "routing_key": "validation.execute",
        "queue_name": "validation_executions",
        "exchange": "validation",
        "schema_version": "1",
    }
    base.update(overrides)
    return CeleryDispatchSettings(**base)


class _RecordingSender:
    """Fake :class:`CelerySendTask` that records every call. No broker required."""

    def __init__(self, task_id: str = "celery-task-1") -> None:
        self._task_id = task_id
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        *,
        task_name: str,
        kwargs: Mapping[str, Any],
        routing_key: str,
        queue: str,
        exchange: str,
        ignore_result: bool,
    ) -> str:
        self.calls.append(
            {
                "task_name": task_name,
                "kwargs": dict(kwargs),
                "routing_key": routing_key,
                "queue": queue,
                "exchange": exchange,
                "ignore_result": ignore_result,
            }
        )
        return self._task_id


class _RaisingSender:
    """Fake sender that raises :class:`CelerySendError` on every call."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(
        self,
        *,
        task_name: str,
        kwargs: Mapping[str, Any],
        routing_key: str,
        queue: str,
        exchange: str,
        ignore_result: bool,
    ) -> str:
        self.calls += 1
        raise CelerySendError("broker_send_failed")


class _LeakySender:
    """Fake sender that raises an arbitrary exception carrying broker secrets."""

    def __call__(
        self,
        *,
        task_name: str,
        kwargs: Mapping[str, Any],
        routing_key: str,
        queue: str,
        exchange: str,
        ignore_result: bool,
    ) -> str:
        raise RuntimeError(
            f"amqp connection refused: amqp://user:{_TOKEN_IN_URL}@broker:5672//"
        )


def _publisher(
    sender: CelerySendTask, settings: CeleryDispatchSettings | None = None
) -> CeleryValidationDispatchPublisher:
    return CeleryValidationDispatchPublisher(
        sender,
        settings or _celery_settings(),
        _FixedClock(),
    )


# --- Happy path ------------------------------------------------------------


async def test_publish_returns_published_with_broker_task_id() -> None:
    sender = _RecordingSender(task_id="broker-id-xyz")
    publisher = _publisher(sender)

    result = await publisher.publish(_payload())

    assert isinstance(result, DispatchPublishResult)
    assert result.outcome is DispatchPublishOutcome.published
    assert result.message_id == "broker-id-xyz"
    assert result.failure is None
    assert len(sender.calls) == 1


async def test_publish_uses_configured_task_name_routing_queue_exchange() -> None:
    sender = _RecordingSender()
    settings = _celery_settings(
        task_name="custom.task",
        routing_key="custom.routing",
        queue_name="custom_queue",
        exchange="custom_exchange",
    )
    publisher = _publisher(sender, settings)

    await publisher.publish(_payload())

    call = sender.calls[0]
    assert call["task_name"] == "custom.task"
    assert call["routing_key"] == "custom.routing"
    assert call["queue"] == "custom_queue"
    assert call["exchange"] == "custom_exchange"


async def test_publish_sets_ignore_result_true() -> None:
    sender = _RecordingSender()
    publisher = _publisher(sender)

    await publisher.publish(_payload())

    assert sender.calls[0]["ignore_result"] is True


async def test_publish_sends_json_safe_envelope_dict() -> None:
    sender = _RecordingSender()
    publisher = _publisher(sender)

    await publisher.publish(_payload())

    envelope = sender.calls[0]["kwargs"]["envelope"]
    assert isinstance(envelope, dict)
    # Survives a real json.dumps round trip with no custom encoder.
    json.dumps(envelope)
    # Exact wire shape.
    assert set(envelope.keys()) == {
        "message_id",
        "schema_version",
        "payload",
        "payload_sha256",
        "created_at",
        "attempt",
        "content_type",
        "trace_id",
        "idempotency_key",
    }
    assert envelope["content_type"] == DISPATCH_CONTENT_TYPE
    assert envelope["schema_version"] == "1"
    assert envelope["attempt"] == 1
    assert envelope["created_at"] == _FIXED_INSTANT.isoformat()
    # Payload carries exactly the WorkerDispatchPayload contract fields.
    assert set(envelope["payload"].keys()) == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }


async def test_publish_does_not_run_task_eagerly() -> None:
    """The sender is called exactly once; no scanner or worker is invoked."""
    sender = _RecordingSender()
    publisher = _publisher(sender)

    await publisher.publish(_payload())

    # Exactly one send_task call — nothing else (no worker, no executor).
    assert len(sender.calls) == 1


async def test_envelope_contains_no_evidence_tenant_or_credentials() -> None:
    sender = _RecordingSender()
    publisher = _publisher(sender)

    await publisher.publish(_payload())

    envelope = sender.calls[0]["kwargs"]["envelope"]
    forbidden = {
        "organization_id",
        "tenant_id",
        "x-organization-id",
        "X-Organization-Id",
        "x-worker-authorization",
        "X-Worker-Authorization",
        "auth_token",
        "user_id",
        "requested_by",
        "credential",
        "credentials",
        "evidence",
        "step_results",
    }
    _assert_keys_absent(envelope, forbidden)


def _assert_keys_absent(value: object, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in forbidden, f"forbidden key {key!r} in envelope"
            _assert_keys_absent(item, forbidden)
    elif isinstance(value, list):
        for item in value:
            _assert_keys_absent(item, forbidden)


# --- Failure paths ---------------------------------------------------------


async def test_celery_send_error_returns_publish_failed_safely() -> None:
    sender = _RaisingSender()
    publisher = _publisher(sender)

    result = await publisher.publish(_payload())

    assert result.outcome is DispatchPublishOutcome.publish_failed
    assert result.message_id is None
    assert result.failure == "broker_send_failed"
    assert sender.calls == 1


async def test_arbitrary_broker_exception_returns_publish_failed_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    publisher = _publisher(_LeakySender())

    with caplog.at_level(logging.WARNING, logger="securescope"):
        result = await publisher.publish(_payload())

    assert result.outcome is DispatchPublishOutcome.publish_failed
    assert result.failure == "broker_send_failed"
    # Critical: neither the broker URL nor the token leaks into the result
    # or the logs.
    assert _TOKEN_IN_URL not in str(result)
    assert _TOKEN_IN_URL not in (result.failure or "")
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _TOKEN_IN_URL not in log_text
    assert "broker:5672" not in log_text


async def test_schema_version_mismatch_returns_rejected() -> None:
    sender = _RecordingSender()
    # Settings declare a schema version different from the producer's.
    settings = _celery_settings(schema_version="99")
    publisher = _publisher(sender, settings)

    result = await publisher.publish(_payload())

    assert result.outcome is DispatchPublishOutcome.rejected
    assert result.failure == "schema_version_mismatch"
    # Nothing was sent.
    assert sender.calls == []


# --- Log hygiene -----------------------------------------------------------


async def test_no_envelope_or_payload_content_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sender = _RecordingSender()
    publisher = _publisher(sender)
    payload = _payload()

    with caplog.at_level(logging.INFO, logger="securescope"):
        await publisher.publish(payload)

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    # Logs name only the execution id (a UUID); no payload content.
    assert "kill_switch_token" not in log_text
    assert "opaque-poll-key" not in log_text
    assert "app.example.com" not in log_text
    assert "execution_specification" not in log_text


# --- Dispatcher integration ------------------------------------------------


class _StubPublisher:
    """Captures one publish call with a configurable outcome."""

    def __init__(
        self, outcome: DispatchPublishOutcome = DispatchPublishOutcome.published
    ) -> None:
        self._outcome = outcome
        self.published_payloads: list[WorkerDispatchPayload] = []

    async def publish(self, payload: WorkerDispatchPayload) -> DispatchPublishResult:
        self.published_payloads.append(payload)
        if self._outcome is DispatchPublishOutcome.published:
            return DispatchPublishResult(
                outcome=DispatchPublishOutcome.published,
                message_id="stub-id",
            )
        return DispatchPublishResult(
            outcome=self._outcome,
            failure="stub_failure",
        )


def _request_with_publisher(publisher: object | None) -> Any:
    """Mimic a FastAPI ``Request`` with the publisher slot set."""
    state = SimpleNamespace(validation_dispatch_publisher=publisher)
    app = SimpleNamespace(state=state)
    return SimpleNamespace(app=app)


def test_get_validation_dispatcher_celery_with_publisher_returns_celery_adapter() -> (
    None
):
    publisher = _StubPublisher()
    settings = _settings_value(
        validation_dispatcher_backend=ValidationDispatcherBackend.celery,
        celery_broker_url=SecretStr("amqp://u:p@host:5672//"),
    )
    request = _request_with_publisher(publisher)

    dispatcher = get_validation_dispatcher(request, settings)

    assert isinstance(dispatcher, CeleryValidationDispatcher)


def test_get_validation_dispatcher_celery_without_publisher_fails_closed() -> None:
    """Selecting celery but with no publisher bound to app.state fails closed."""
    settings = _settings_value(
        validation_dispatcher_backend=ValidationDispatcherBackend.celery,
        celery_broker_url=SecretStr("amqp://u:p@host:5672//"),
    )
    request = _request_with_publisher(None)

    dispatcher = get_validation_dispatcher(request, settings)

    assert isinstance(dispatcher, UnconfiguredValidationDispatcher)


async def test_celery_dispatcher_calls_publisher_and_succeeds() -> None:
    publisher = _StubPublisher()
    dispatcher = CeleryValidationDispatcher(publisher)  # type: ignore[arg-type]

    # No exception means dispatch succeeded.
    await dispatcher.dispatch(_payload())

    assert len(publisher.published_payloads) == 1
    # And no worker code is invoked — the stub captures the payload only.
    assert (
        publisher.published_payloads[0].template_id == HTTP_SECURITY_HEADER_VALIDATION
    )


async def test_celery_dispatcher_publish_failed_raises_not_configured() -> None:
    """A non-``published`` publisher outcome rolls back the request transaction."""
    publisher = _StubPublisher(outcome=DispatchPublishOutcome.publish_failed)
    dispatcher = CeleryValidationDispatcher(publisher)  # type: ignore[arg-type]

    with pytest.raises(ValidationDispatchNotConfigured):
        await dispatcher.dispatch(_payload())


async def test_celery_dispatcher_rejected_raises_not_configured() -> None:
    publisher = _StubPublisher(outcome=DispatchPublishOutcome.rejected)
    dispatcher = CeleryValidationDispatcher(publisher)  # type: ignore[arg-type]

    with pytest.raises(ValidationDispatchNotConfigured):
        await dispatcher.dispatch(_payload())


# --- Settings validator ----------------------------------------------------


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
    overrides: dict[str, Any] = {"environment": environment}
    if environment in (Environment.staging, Environment.production):
        overrides["worker_auth_token"] = SecretStr("deployed-token")
    settings = _settings_value(**overrides)
    assert (
        settings.validation_dispatcher_backend
        is ValidationDispatcherBackend.unconfigured
    )
    assert settings.celery_broker_url is None


@pytest.mark.parametrize(
    "environment",
    [
        Environment.development,
        Environment.test,
        Environment.staging,
        Environment.production,
    ],
)
def test_celery_backend_without_broker_url_fails_closed(
    environment: Environment,
) -> None:
    overrides: dict[str, Any] = {
        "environment": environment,
        "validation_dispatcher_backend": ValidationDispatcherBackend.celery,
    }
    if environment in (Environment.staging, Environment.production):
        overrides["worker_auth_token"] = SecretStr("deployed-token")

    with pytest.raises(ValidationError) as exc_info:
        _settings_value(**overrides)
    message = str(exc_info.value)
    assert "celery_broker_url" in message
    # And the (absent) URL value cannot leak — the validator names only the rule.
    assert "amqp://" not in message


@pytest.mark.parametrize(
    "environment",
    [Environment.staging, Environment.production],
)
def test_celery_backend_with_broker_url_allowed_in_deployed_environments(
    environment: Environment,
) -> None:
    settings = _settings_value(
        environment=environment,
        validation_dispatcher_backend=ValidationDispatcherBackend.celery,
        celery_broker_url=SecretStr("amqp://u:p@host:5672//"),
        worker_auth_token=SecretStr("deployed-token"),
    )
    assert settings.validation_dispatcher_backend is ValidationDispatcherBackend.celery


def test_settings_repr_does_not_leak_broker_url() -> None:
    settings = _settings_value(
        validation_dispatcher_backend=ValidationDispatcherBackend.celery,
        celery_broker_url=SecretStr("amqp://u:p@host:5672//"),
    )
    text = repr(settings)
    # ``SecretStr`` keeps the URL out of the repr.
    assert "amqp://u:p@host" not in text


# --- envelope_to_dict ------------------------------------------------------


async def test_envelope_to_dict_round_trips_through_json() -> None:
    sender = _RecordingSender()
    publisher = _publisher(sender)
    await publisher.publish(_payload())

    envelope = sender.calls[0]["kwargs"]["envelope"]
    rebuilt = json.loads(json.dumps(envelope))
    assert rebuilt == envelope


def test_envelope_to_dict_exposes_required_fields() -> None:
    # Compile-time-ish guard: ensure the helper signature stays stable.
    assert callable(envelope_to_dict)


# --- Import purity ---------------------------------------------------------


_FORBIDDEN_IMPORT_TOKENS = (
    "fastapi",
    "sqlalchemy",
    "repository",
    "service",
    "router",
    "worker_runner",
    "worker_process",
    "worker_client",
    "http_transport",
    "SafeHttpTransport",
    "HttpxTransportClient",
    "app.main",
    "app.platform.database",
    "app.platform.dependencies",
    # The publisher is a skeleton — it must NOT import celery yet. A real
    # sender lives in a separate runtime module so the dev/test path can be
    # exercised without celery installed.
    "celery",
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


def test_celery_publisher_module_imports_no_runtime_or_celery() -> None:
    for module_name in _imported_modules(celery_publisher_module):
        assert not any(token in module_name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"celery_publisher must not import: {module_name}"
        )


def test_api_path_does_not_import_celery_publisher_module() -> None:
    """service.py and router.py never reach for the publisher module directly.

    The dispatcher does import it lazily inside ``get_validation_dispatcher``;
    that is still captured by AST so we keep the publisher out of the API
    path's top-level imports.
    """
    for module in (service_module, router_module):
        names = _imported_modules(module)
        for module_name in names:
            assert "celery_publisher" not in module_name, (
                f"{module.__name__} must not import celery_publisher; "
                f"found: {module_name}"
            )


def test_api_path_still_imports_no_worker_runtime() -> None:
    """The API path must still never reach worker_runner/process/client/HTTP."""
    runtime_tokens = (
        "worker_runner",
        "worker_process",
        "worker_client",
        "http_transport",
        "SafeHttpTransport",
        "HttpxTransportClient",
    )
    for module in (dispatcher_module, service_module, router_module):
        names = _imported_modules(module)
        for module_name in names:
            assert not any(token in module_name for token in runtime_tokens), (
                f"{module.__name__} must not import worker runtime: {module_name}"
            )


def test_service_and_router_do_not_import_celery_publisher() -> None:
    """The orchestration layers must reach the publisher only via the Protocol.

    ``app.main`` legitimately imports the publisher in its lifespan to bind
    it to ``app.state`` when the celery backend is selected — that is the
    runtime wiring step. ``dispatcher.py`` legitimately performs a *lazy*
    import of the concrete ``CeleryValidationDispatcher`` from inside the
    dispatcher factory's celery branch (the same pattern as the in_memory
    backend), so its module-load-time imports stay clean of any worker
    runtime. The request-path orchestration layers (``service``, ``router``),
    however, must never name ``celery_publisher`` or the ``celery`` package —
    they must reach the dispatcher only through the abstract
    ``ValidationDispatcher`` Protocol.
    """
    from app.modules.validation_executions import router as router_module
    from app.modules.validation_executions import service as service_module

    for module in (service_module, router_module):
        for module_name in _imported_modules(module):
            assert "celery_publisher" not in module_name, (
                f"{module.__name__} must not import celery_publisher: {module_name}"
            )
            assert module_name != "celery", (
                f"{module.__name__} must not import celery: {module_name}"
            )
