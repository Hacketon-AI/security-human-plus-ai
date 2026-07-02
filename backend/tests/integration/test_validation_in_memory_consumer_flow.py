"""Integration test for the dev-only in-memory consumer end-to-end.

Exercises the full lifecycle end-to-end: the API enqueues an execution (and
*only* enqueues — no worker runs in the API process), the dev consumer
dequeues the message, sends ``worker-started`` (queued → executing), runs the
worker with a fake scanner transport (no network), sends ``worker-finished``,
and the user's ``GET`` then shows the terminal status. Without
Docker/Testcontainers the test is reported as blocked — never silently
substituted with a different DB.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

import pytest
from app.config import Environment, Settings, ValidationDispatcherBackend
from app.main import create_app
from app.modules.validation_executions.executor_transport import (
    HttpResponse,
    HttpTransport,
)
from app.modules.validation_executions.in_memory_consumer import (
    ConsumerOutcome,
    consume_once,
)
from app.modules.validation_executions.in_memory_queue import InMemoryDispatchQueue
from app.modules.validation_executions.worker_client import WorkerClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.conftest import WORKER_AUTH_TOKEN, tenant_headers
from tests.integration.test_validation_executions_api import _create_body, _setup

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]

_STRONG_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=()",
}


class _FakeScannerTransport:
    """Read-only transport for the scanner side — returns canned strong headers."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        return HttpResponse(200, _STRONG_HEADERS, url, 5.0)


def _scanner_factory(
    scope: Mapping[str, Any], safety: Mapping[str, Any]
) -> HttpTransport:
    return _FakeScannerTransport()


class _AsgiResultTransport:
    """Worker hook transport that POSTs through the test ASGI client.

    Keeps the integration test self-contained (no real network) while still
    exercising the real ``worker-started`` and ``worker-finished`` handlers
    under the worker credential.
    """

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: Mapping[str, str],
    ) -> Any:
        response = await self._client.post(url, json=json_body, headers=dict(headers))
        return _Status(response.status_code)


class _Status:
    __slots__ = ("status_code",)

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.fixture
async def in_memory_consumer_app(
    migrated_dsn: str, engine: AsyncEngine
) -> AsyncIterator[tuple[AsyncClient, InMemoryDispatchQueue]]:
    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(migrated_dsn),
        validation_dispatcher_backend=ValidationDispatcherBackend.in_memory,
        worker_auth_token=SecretStr(WORKER_AUTH_TOKEN),
        # The dev in-memory consumer drives the API hooks with the shared
        # worker token (no per-execution credential is minted in this
        # adapter). Step 3 made the shared token the transitional
        # fallback path; this fixture enables it so the existing
        # lifecycle coverage keeps exercising the same surface.
        worker_shared_token_fallback_enabled=True,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        queue = app.state.validation_dispatch_queue
        assert isinstance(queue, InMemoryDispatchQueue)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, queue


async def test_create_execution_only_enqueues_and_does_not_run_worker(
    in_memory_consumer_app: tuple[AsyncClient, InMemoryDispatchQueue],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[Any],
) -> None:
    client, queue = in_memory_consumer_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )

    assert resp.status_code == 201
    # The API path only enqueued. No worker ran inline.
    body = resp.json()
    assert body["status"] == "queued"
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert body["step_results"] == []
    assert queue.size() == 1


async def test_consumer_drives_full_lifecycle_started_then_finished(
    in_memory_consumer_app: tuple[AsyncClient, InMemoryDispatchQueue],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[Any],
) -> None:
    client, queue = in_memory_consumer_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])

    create = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=headers,
    )
    execution_id = create.json()["id"]
    assert queue.size() == 1

    worker_client = WorkerClient(
        base_url="http://testserver",
        transport=_AsgiResultTransport(client),  # type: ignore[arg-type]
        auth_token=SecretStr(WORKER_AUTH_TOKEN),
    )

    result = await consume_once(
        queue,
        worker_client,
        transport_factory=_scanner_factory,
    )

    # The consumer posted started → ran the worker → posted finished.
    assert result.outcome is ConsumerOutcome.delivered
    assert result.started_delivery is not None and result.started_delivery.delivered
    assert result.finished_delivery is not None and result.finished_delivery.delivered
    # The queue is empty (at-most-once delivery).
    assert queue.size() == 0

    # The user's GET reflects the terminal lifecycle state and the worker's
    # sanitized result.
    get = await client.get(
        f"/api/v1/validation-executions/{execution_id}", headers=headers
    )
    assert get.status_code == 200
    body = get.json()
    assert body["status"] in {"succeeded", "failed"}
    assert body["started_at"] is not None
    assert body["finished_at"] is not None
    # Strong headers in the canned response → a definitive verdict. The
    # executor treats "missing/weak headers" as the validation hypothesis, so
    # strong headers reach the run's other definitive outcome (``not_reproduced``).
    assert body["outcome"] in {"validated", "not_reproduced"}
    # Step results were persisted from the worker's sanitized payload.
    assert body["step_results"]


async def test_runner_failure_after_started_recovers_into_terminal_failed_safely(
    in_memory_consumer_app: tuple[AsyncClient, InMemoryDispatchQueue],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[Any],
) -> None:
    """A runner crash after worker-started must NOT leave the row in executing.

    The consumer must recover into a sanitized ``failed_safely``
    ``worker-finished`` so the user's ``GET`` shows a terminal failed state
    with ``outcome=failed_safely`` and ``finished_at`` set — never stuck at
    ``executing``.
    """

    class _ExplodingScannerFactory:
        """Simulates a runner crash by raising when the scanner transport is built."""

        def __call__(
            self, scope: Mapping[str, Any], safety: Mapping[str, Any]
        ) -> HttpTransport:
            raise RuntimeError(
                "simulated runner crash with target=https://leaked-target.example"
            )

    client, queue = in_memory_consumer_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])

    create = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=headers,
    )
    execution_id = create.json()["id"]
    assert queue.size() == 1

    worker_client = WorkerClient(
        base_url="http://testserver",
        transport=_AsgiResultTransport(client),  # type: ignore[arg-type]
        auth_token=SecretStr(WORKER_AUTH_TOKEN),
    )

    result = await consume_once(
        queue, worker_client, transport_factory=_ExplodingScannerFactory()
    )

    # The consumer recovered into a sanitized failed_safely worker-finished.
    assert result.outcome is ConsumerOutcome.delivered
    assert result.started_delivery is not None and result.started_delivery.delivered
    assert result.finished_delivery is not None and result.finished_delivery.delivered
    assert queue.size() == 0

    # GET reflects the terminal failed state — not stuck in executing.
    get = await client.get(
        f"/api/v1/validation-executions/{execution_id}", headers=headers
    )
    assert get.status_code == 200
    body = get.json()
    assert body["status"] == "failed"
    assert body["outcome"] == "failed_safely"
    assert body["error_code"] == "worker_runtime_failed"
    # ``error_message`` is sanitized away — never echoes the raw exception.
    assert body["error_message"] is None
    assert body["started_at"] is not None
    assert body["finished_at"] is not None
    # And no leak in the persisted result fields.
    response_text = get.text
    assert "leaked-target.example" not in response_text


async def test_consume_once_no_message_when_nothing_queued(
    in_memory_consumer_app: tuple[AsyncClient, InMemoryDispatchQueue],
) -> None:
    client, queue = in_memory_consumer_app
    worker_client = WorkerClient(
        base_url="http://testserver",
        transport=_AsgiResultTransport(client),  # type: ignore[arg-type]
        auth_token=SecretStr(WORKER_AUTH_TOKEN),
    )

    result = await consume_once(
        queue, worker_client, transport_factory=_scanner_factory
    )

    assert result.outcome is ConsumerOutcome.no_message
    assert result.message_id is None
    assert result.started_delivery is None
    assert result.finished_delivery is None
