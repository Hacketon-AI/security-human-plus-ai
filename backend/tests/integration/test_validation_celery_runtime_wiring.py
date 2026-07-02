"""Integration tests for the Celery dispatch runtime wiring.

End-to-end: the FastAPI app is started with ``validation_dispatcher_backend
= celery`` against a real PostgreSQL container, the lifespan binds a
:class:`CeleryValidationDispatchPublisher`, and the resolved dispatcher is
:class:`CeleryValidationDispatcher`. The Celery app's ``send_task`` is
replaced with a fake before the request runs so no live RabbitMQ is
required. If Docker/Testcontainers is unavailable the suite reports
blocked/skipped — never silently substituting SQLite.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from app.config import Environment, Settings, ValidationDispatcherBackend
from app.main import create_app
from app.modules.validation_executions.celery_publisher import (
    CeleryValidationDispatcher,
    CeleryValidationDispatchPublisher,
)
from app.modules.validation_executions.dispatcher import get_validation_dispatcher
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.conftest import WORKER_AUTH_TOKEN, tenant_headers
from tests.integration.test_validation_executions_api import (
    _create_body,
    _setup,
)

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]

_BROKER_URL = "amqp://user:pa55w0rd@rabbit.test:5672//"


class _FakeSendTask:
    """Records every publish call. Matches the CelerySendTask Protocol.

    Replaces the publisher's sender directly (no Celery involved), so the
    signature mirrors the Protocol the publisher calls — keyword-only,
    with ``task_name`` rather than Celery's positional ``name``.
    """

    def __init__(self) -> None:
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
        return f"task-{len(self.calls)}"


@pytest.fixture
async def celery_dispatch_app(
    migrated_dsn: str, engine: AsyncEngine
) -> AsyncIterator[tuple[AsyncClient, _FakeSendTask, Any]]:
    """App wired to the Celery backend, with ``send_task`` replaced by a fake.

    Yields ``(client, fake_send_task, app)``. The Celery app's
    ``send_task`` is monkey-patched after the lifespan binds the publisher,
    so the production wiring is exercised end-to-end without contacting
    any broker.
    """
    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(migrated_dsn),
        validation_dispatcher_backend=ValidationDispatcherBackend.celery,
        celery_broker_url=SecretStr(_BROKER_URL),
        worker_auth_token=SecretStr(WORKER_AUTH_TOKEN),
    )
    app = create_app(settings)
    fake = _FakeSendTask()
    async with app.router.lifespan_context(app):
        # The lifespan has bound a publisher whose sender wraps the real
        # Celery app's send_task. Replace the sender with one that uses
        # our fake so no broker is contacted in the test.
        publisher = app.state.validation_dispatch_publisher
        assert isinstance(publisher, CeleryValidationDispatchPublisher)
        publisher._sender = fake  # type: ignore[attr-defined]
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, fake, app


async def test_lifespan_binds_celery_publisher_and_dispatcher(
    celery_dispatch_app: tuple[AsyncClient, _FakeSendTask, Any],
) -> None:
    _client, _fake, app = celery_dispatch_app
    publisher = app.state.validation_dispatch_publisher
    assert isinstance(publisher, CeleryValidationDispatchPublisher)
    # The dispatcher resolves to the Celery variant when the publisher slot
    # is populated.
    fake_request = SimpleNamespace(app=app)
    dispatcher = get_validation_dispatcher(fake_request, settings=app.state.settings)  # type: ignore[arg-type]
    assert isinstance(dispatcher, CeleryValidationDispatcher)


async def test_create_execution_publishes_one_envelope_to_broker(
    celery_dispatch_app: tuple[AsyncClient, _FakeSendTask, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[Any],
) -> None:
    client, fake, _app = celery_dispatch_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )

    assert resp.status_code == 201
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["task_name"] == "validation_executions.run_validation"
    assert call["routing_key"] == "validation.execute"
    assert call["queue"] == "validation_executions"
    assert call["exchange"] == "validation"
    assert call["ignore_result"] is True
    # The kwargs carry an envelope with exactly the contract payload field
    # set — no tenant identity, no credentials, no evidence.
    envelope = call["kwargs"]["envelope"]
    assert set(envelope["payload"].keys()) == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }
    assert envelope["payload"]["execution_id"] == resp.json()["id"]
