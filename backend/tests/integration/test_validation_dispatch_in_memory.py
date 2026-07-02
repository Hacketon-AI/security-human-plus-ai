"""Integration tests for the development-only in-memory dispatch backend.

End-to-end: the API creates a validation execution, the dispatcher serializes
the frozen payload, and the in-memory queue holds a JSON-safe message — no
worker is started, no scanner runs in the API process. Idempotency is also
exercised here because it lives at the service boundary and must short-circuit
*before* dispatch (so a repeat request never enqueues twice).
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from app.config import Environment, Settings, ValidationDispatcherBackend
from app.main import create_app
from app.modules.validation_executions.in_memory_queue import InMemoryDispatchQueue
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from tests.conftest import tenant_headers
from tests.integration.test_validation_executions_api import (
    _create_body,
    _setup,
)

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]

_CONTRACT_FIELDS = frozenset(
    {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }
)


@pytest.fixture
async def in_memory_dispatch_app(
    migrated_dsn: str, engine: AsyncEngine
) -> AsyncIterator[tuple[AsyncClient, InMemoryDispatchQueue]]:
    """Build a development app wired to the in-memory dispatch backend.

    Yields the HTTP client and the actual queue instance the app uses, so
    tests can assert the queue's observed state without indirection.
    """
    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(migrated_dsn),
        validation_dispatcher_backend=ValidationDispatcherBackend.in_memory,
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


async def test_create_enqueues_exactly_one_json_safe_message(
    in_memory_dispatch_app: tuple[AsyncClient, InMemoryDispatchQueue],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[Any],
) -> None:
    client, queue = in_memory_dispatch_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )

    assert resp.status_code == 201
    assert queue.size() == 1

    item = queue.dequeue()
    assert item is not None
    # The queued message is exactly the JSON-safe contract — nothing more.
    assert set(item.message.keys()) == _CONTRACT_FIELDS
    # Survives a real json.dumps round trip with no custom encoder.
    json.dumps(item.message)
    # The frozen payload's execution_id matches the API response.
    assert item.message["execution_id"] == resp.json()["id"]


async def test_idempotent_repeat_does_not_enqueue_twice(
    in_memory_dispatch_app: tuple[AsyncClient, InMemoryDispatchQueue],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[Any],
) -> None:
    client, queue = in_memory_dispatch_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    body = _create_body(ctx, idempotency_key="rep-1")

    first = await client.post(
        "/api/v1/validation-executions", json=body, headers=headers
    )
    second = await client.post(
        "/api/v1/validation-executions", json=body, headers=headers
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    # The repeat short-circuits before dispatch: the queue size is unchanged.
    assert queue.size() == 1


async def test_no_tenant_or_credential_fields_in_queued_message(
    in_memory_dispatch_app: tuple[AsyncClient, InMemoryDispatchQueue],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[Any],
) -> None:
    client, queue = in_memory_dispatch_app
    ctx = await _setup(client, create_organization, session_factory)

    await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )

    item = queue.dequeue()
    assert item is not None
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
    _assert_keys_absent(item.message, forbidden)


def _assert_keys_absent(value: object, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in forbidden, f"forbidden key {key!r} in queued message"
            _assert_keys_absent(item, forbidden)
    elif isinstance(value, list):
        for item in value:
            _assert_keys_absent(item, forbidden)
