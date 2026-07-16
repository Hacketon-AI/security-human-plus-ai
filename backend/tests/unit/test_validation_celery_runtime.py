"""Unit tests for the Celery runtime wiring.

Cover only the publisher-side runtime: building the Celery app from
settings, wrapping ``send_task`` in a safe :class:`CelerySendTask`, and the
app-lifespan binding that puts a :class:`CeleryValidationDispatchPublisher`
into ``app.state``. The worker consumer is deliberately not exercised — it
is not implemented.

These tests never require a live RabbitMQ: Celery's app object does not
connect on construction, and the sender is exercised against a fake Celery
where ``send_task`` is monkey-patched. The lifespan binding is exercised
without starting the database engine (the engine connects lazily, and the
lifespan never touches it).
"""

import ast
import logging
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.config import Environment, Settings, ValidationDispatcherBackend
from app.main import _lifespan, create_app
from app.modules.validation_executions import celery_runtime as celery_runtime_module
from app.modules.validation_executions.celery_publisher import (
    CelerySendError,
    CeleryValidationDispatcher,
    CeleryValidationDispatchPublisher,
)
from app.modules.validation_executions.celery_runtime import (
    create_validation_celery_app,
    make_celery_sender,
)
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatcher import (
    UnconfiguredValidationDispatcher,
    get_validation_dispatcher,
)
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION
from celery import Celery
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError

_DSN = "postgresql+asyncpg://securescope:secret@localhost:5432/securescope"
_BROKER_URL = "amqp://user:pa55w0rd@rabbit.test:5672//"


def _payload() -> WorkerDispatchPayload:
    return WorkerDispatchPayload(
        execution_id="11111111-1111-1111-1111-111111111111",
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


def _celery_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": Environment.development,
        "database_dsn": SecretStr(_DSN),
        "validation_dispatcher_backend": ValidationDispatcherBackend.celery,
        "celery_broker_url": SecretStr(_BROKER_URL),
    }
    base.update(overrides)
    if base["environment"] in (Environment.staging, Environment.production):
        base.setdefault("jwt_secret", SecretStr("test-only-deployed-jwt-secret"))
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


# --- create_validation_celery_app -------------------------------------------


def test_app_construction_uses_broker_url_without_leaking_it_in_repr() -> None:
    settings = _celery_settings()
    app = create_validation_celery_app(settings.celery_broker_url)

    assert isinstance(app, Celery)
    # The URL reaches Celery's internal config but stays out of any
    # SecureScope-owned representation. The Settings repr also never
    # contains the cleartext URL (SecretStr enforces this) — verify.
    assert _BROKER_URL not in repr(settings)
    assert "pa55w0rd" not in repr(settings)


def test_app_has_result_backend_disabled() -> None:
    app = create_validation_celery_app(_celery_settings().celery_broker_url)
    # ``conf.result_backend`` returns None for a disabled backend; the
    # default would be an empty string. Either way "no Redis result
    # backend" must hold.
    assert app.conf.result_backend in (None, "")
    assert app.conf.task_ignore_result is True


def test_app_does_not_run_tasks_eagerly() -> None:
    app = create_validation_celery_app(_celery_settings().celery_broker_url)
    assert app.conf.task_always_eager is False


def test_app_refuses_non_json_serializers() -> None:
    app = create_validation_celery_app(_celery_settings().celery_broker_url)
    assert app.conf.task_serializer == "json"
    assert list(app.conf.accept_content) == ["json"]


def test_app_construction_without_broker_url_raises() -> None:
    # Defense in depth: even if a caller bypasses the Settings validator,
    # the factory refuses to construct an app without a broker URL.
    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(_DSN),
        _env_file=None,
        validation_dispatcher_backend=ValidationDispatcherBackend.unconfigured,
    )
    with pytest.raises(RuntimeError, match="celery_broker_url"):
        create_validation_celery_app(settings.celery_broker_url)


# --- make_celery_sender -----------------------------------------------------


def _fake_celery_with_send(captured: dict[str, Any], task_id: str = "task-1") -> Celery:
    """A Celery app whose ``send_task`` records its arguments and returns an id."""

    app = Celery("test")

    def fake_send_task(
        name: str,
        *,
        kwargs: dict[str, Any] | None = None,
        routing_key: str | None = None,
        queue: str | None = None,
        exchange: str | None = None,
        ignore_result: bool = False,
        **extra: Any,
    ) -> SimpleNamespace:
        captured["name"] = name
        captured["kwargs"] = kwargs
        captured["routing_key"] = routing_key
        captured["queue"] = queue
        captured["exchange"] = exchange
        captured["ignore_result"] = ignore_result
        captured["extra"] = extra
        return SimpleNamespace(id=task_id)

    app.send_task = fake_send_task  # type: ignore[method-assign]
    return app


def test_sender_forwards_addressing_and_returns_task_id() -> None:
    captured: dict[str, Any] = {}
    app = _fake_celery_with_send(captured, task_id="broker-task-42")
    sender = make_celery_sender(app)

    task_id = sender(
        task_name="validation_executions.run_validation",
        kwargs={"envelope": {"message_id": "m-1"}},
        routing_key="validation.execute",
        queue="validation_executions",
        exchange="validation",
        ignore_result=True,
    )

    assert task_id == "broker-task-42"
    assert captured["name"] == "validation_executions.run_validation"
    assert captured["kwargs"] == {"envelope": {"message_id": "m-1"}}
    assert captured["routing_key"] == "validation.execute"
    assert captured["queue"] == "validation_executions"
    assert captured["exchange"] == "validation"
    assert captured["ignore_result"] is True
    # No extra arguments leak through; eager/get is never requested.
    assert captured["extra"] == {}


def test_sender_does_not_call_apply_async_or_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    app = _fake_celery_with_send(captured)

    sentinel = MagicMock(side_effect=AssertionError("apply_async must not be called"))
    monkeypatch.setattr(app, "send_task", app.send_task)  # exercise via send_task only

    # Spy on apply_async/AsyncResult.get to confirm they are never reached.
    apply_async_called = MagicMock(side_effect=AssertionError("apply_async called"))
    monkeypatch.setattr(Celery, "tasks", {})  # type: ignore[arg-type]
    monkeypatch.setattr(
        "celery.app.task.Task.apply_async",
        apply_async_called,
        raising=False,
    )
    _ = sentinel  # quiet linter

    sender = make_celery_sender(app)
    sender(
        task_name="t",
        kwargs={},
        routing_key="rk",
        queue="q",
        exchange="ex",
        ignore_result=True,
    )
    apply_async_called.assert_not_called()


def test_sender_maps_broker_exception_to_celery_send_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = Celery("test")

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        # Realistic kombu-like message that DOES carry the broker URL.
        raise ConnectionError(
            "Cannot connect to amqp://user:pa55w0rd@rabbit.test:5672//"
        )

    app.send_task = boom  # type: ignore[method-assign]

    sender = make_celery_sender(app)
    caplog.set_level(logging.WARNING, logger="securescope.validation.celery_runtime")

    with pytest.raises(CelerySendError) as exc_info:
        sender(
            task_name="validation_executions.run_validation",
            kwargs={"envelope": {"payload": {"target": "https://secret.test"}}},
            routing_key="rk",
            queue="q",
            exchange="ex",
            ignore_result=True,
        )

    # The CelerySendError carries only the static category.
    assert str(exc_info.value) == "broker_send_failed"
    # The exception chain is suppressed so the original (URL-bearing)
    # exception cannot resurface in a traceback.
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is not None  # implicit context still exists
    assert exc_info.value.__suppress_context__ is True

    # Logs never contain the broker URL, credentials, or the envelope.
    for record in caplog.records:
        message = record.getMessage()
        assert "pa55w0rd" not in message
        assert "amqp://" not in message
        assert "https://secret.test" not in message
        assert "envelope" not in message


def test_sender_log_message_carries_no_kwargs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = Celery("test")

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("kombu OperationalError: tcp://broker.internal")

    app.send_task = boom  # type: ignore[method-assign]
    sender = make_celery_sender(app)
    caplog.set_level(logging.WARNING, logger="securescope.validation.celery_runtime")

    with pytest.raises(CelerySendError):
        sender(
            task_name="validation_executions.run_validation",
            kwargs={"envelope": {"payload": {"target": "https://leaky.test"}}},
            routing_key="rk",
            queue="q",
            exchange="ex",
            ignore_result=True,
        )
    messages = [record.getMessage() for record in caplog.records]
    assert all("envelope" not in m for m in messages)
    assert all("leaky" not in m for m in messages)
    assert all("broker.internal" not in m for m in messages)


# --- Lifespan binding ------------------------------------------------------


async def _run_lifespan(app: FastAPI) -> None:
    """Drive the lifespan once so app.state slots are populated."""
    async with _lifespan(app):
        pass


def _build_app(settings: Settings) -> FastAPI:
    """Build an app and pre-populate the bits the lifespan reads.

    The lifespan reads ``settings`` and creates the database engine, but
    never connects (asyncpg connects lazily). The dispatch-backend binding
    is independent of the database, so this is enough for binding tests.
    """
    return create_app(settings)


async def test_lifespan_binds_publisher_for_celery_backend() -> None:
    app = _build_app(_celery_settings())
    await _run_lifespan(app)

    publisher = app.state.validation_dispatch_publisher
    assert isinstance(publisher, CeleryValidationDispatchPublisher)
    # The in-memory queue slot stays None for the celery backend.
    assert app.state.validation_dispatch_queue is None


async def test_lifespan_does_not_bind_publisher_for_in_memory_backend() -> None:
    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(_DSN),
        _env_file=None,
        validation_dispatcher_backend=ValidationDispatcherBackend.in_memory,
    )
    app = _build_app(settings)
    await _run_lifespan(app)

    assert app.state.validation_dispatch_publisher is None
    # in_memory branch DOES set up its queue.
    assert app.state.validation_dispatch_queue is not None


async def test_lifespan_does_not_bind_publisher_for_unconfigured_backend() -> None:
    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(_DSN),
        _env_file=None,
        validation_dispatcher_backend=ValidationDispatcherBackend.unconfigured,
    )
    app = _build_app(settings)
    await _run_lifespan(app)

    assert app.state.validation_dispatch_publisher is None
    assert app.state.validation_dispatch_queue is None


# --- Dispatcher resolution against the bound publisher ---------------------


async def test_get_validation_dispatcher_returns_celery_when_publisher_bound() -> None:
    settings = _celery_settings()
    app = _build_app(settings)
    await _run_lifespan(app)

    fake_request = SimpleNamespace(app=app)
    dispatcher = get_validation_dispatcher(fake_request, settings=settings)  # type: ignore[arg-type]
    assert isinstance(dispatcher, CeleryValidationDispatcher)


async def test_dispatcher_fails_closed_when_celery_publisher_missing() -> None:
    settings = _celery_settings()
    # Build an app but don't run lifespan: publisher slot stays absent.
    app = _build_app(settings)

    fake_request = SimpleNamespace(app=app)
    dispatcher = get_validation_dispatcher(fake_request, settings=settings)  # type: ignore[arg-type]
    assert isinstance(dispatcher, UnconfiguredValidationDispatcher)


# --- Settings gate ---------------------------------------------------------


@pytest.mark.parametrize(
    "environment",
    [
        Environment.development,
        Environment.test,
        Environment.staging,
        Environment.production,
    ],
)
def test_celery_backend_without_broker_url_fails_settings(
    environment: Environment,
) -> None:
    overrides: dict[str, object] = {
        "environment": environment,
        "database_dsn": SecretStr(_DSN),
        "validation_dispatcher_backend": ValidationDispatcherBackend.celery,
        "_env_file": None,
    }
    if environment in (Environment.staging, Environment.production):
        overrides["jwt_secret"] = SecretStr("test-only-deployed-jwt-secret")
        overrides["worker_auth_token"] = SecretStr("deployed-token")
    with pytest.raises(ValidationError) as exc_info:
        Settings(**overrides)  # type: ignore[arg-type]
    message = str(exc_info.value)
    assert "celery_broker_url" in message


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_celery_backend_with_broker_url_allowed_in_deployed(
    environment: Environment,
) -> None:
    settings = Settings(
        environment=environment,
        database_dsn=SecretStr(_DSN),
        _env_file=None,
        jwt_secret=SecretStr("test-only-deployed-jwt-secret"),
        validation_dispatcher_backend=ValidationDispatcherBackend.celery,
        celery_broker_url=SecretStr(_BROKER_URL),
        worker_auth_token=SecretStr("deployed-token"),
    )
    assert settings.validation_dispatcher_backend is ValidationDispatcherBackend.celery


def test_default_dispatcher_backend_remains_unconfigured() -> None:
    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(_DSN),
        _env_file=None,
    )
    assert (
        settings.validation_dispatcher_backend
        is ValidationDispatcherBackend.unconfigured
    )


# --- Import purity ---------------------------------------------------------


_RUNTIME_FORBIDDEN_TOKENS = (
    "worker_runner",
    "worker_process",
    "worker_client",
    "http_transport",
    "SafeHttpTransport",
    "HttpxTransportClient",
    "fastapi",
    "sqlalchemy",
    "repository",
    "service",
    "router",
)

_API_FORBIDDEN_TOKENS = (
    "worker_runner",
    "worker_process",
    "worker_client",
    "http_transport",
    "SafeHttpTransport",
    "HttpxTransportClient",
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


def test_celery_runtime_import_purity() -> None:
    for module_name in _imported_modules(celery_runtime_module):
        assert not any(token in module_name for token in _RUNTIME_FORBIDDEN_TOKENS), (
            f"celery_runtime.py must not import: {module_name}"
        )


def test_api_path_does_not_import_worker_runtime() -> None:
    # Re-pin the long-standing rule now that the lifespan has a Celery
    # branch: app.main / router / service / dispatcher still must not
    # import the worker runtime or its HTTP transport.
    from app.main import __file__ as main_file
    from app.modules.validation_executions import (
        dispatcher as dispatcher_module,
    )
    from app.modules.validation_executions import (
        router as router_module,
    )
    from app.modules.validation_executions import (
        service as service_module,
    )

    main_module = SimpleNamespace(__file__=main_file)
    for module in (main_module, router_module, service_module, dispatcher_module):
        for module_name in _imported_modules(module):
            assert not any(token in module_name for token in _API_FORBIDDEN_TOKENS), (
                f"{module} must not import worker runtime: {module_name}"
            )


# --- Sanity: a publisher Mapping covers the wire contract field set --------


def test_publisher_round_trips_a_payload_through_the_fake_sender() -> None:
    """Smoke test that the wired publisher hands the envelope to the sender.

    The detailed envelope/payload assertions live in the celery_publisher
    unit tests; this one just confirms the runtime-built publisher works
    end-to-end with a fake sender (no broker, no eager mode).
    """

    captured: dict[str, Any] = {}
    app = _fake_celery_with_send(captured, task_id="ok")
    sender = make_celery_sender(app)

    from app.modules.validation_executions.celery_publisher import (
        CeleryDispatchSettings,
        CeleryValidationDispatchPublisher,
    )
    from app.platform.clock import SystemClock

    publisher = CeleryValidationDispatchPublisher(
        sender,
        CeleryDispatchSettings(
            task_name="validation_executions.run_validation",
            routing_key="validation.execute",
            queue_name="validation_executions",
            exchange="validation",
            schema_version="1",
        ),
        SystemClock(),
    )

    import asyncio

    result = asyncio.run(publisher.publish(_payload()))
    assert result.outcome.value == "published"
    assert result.message_id == "ok"
    # The sender saw an envelope kwarg with exactly the contract payload fields.
    envelope: Mapping[str, Any] = captured["kwargs"]["envelope"]
    assert set(envelope["payload"].keys()) == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }
