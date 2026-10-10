"""The console reads real runtime configuration, never hardcoded status."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from tests.conftest import tenant_headers

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]


async def test_system_status_reports_configured_values(
    client: AsyncClient, create_organization: CreateOrg
) -> None:
    org = await create_organization()

    response = await client.get(
        "/api/v1/system/status", headers=tenant_headers(org["id"])
    )

    assert response.status_code == 200
    assert response.json() == {
        "environment": "development",
        "dispatcher_backend": "unconfigured",
        "ai_router_mode": "deterministic",
        "claude_configured": False,
        "fireworks_configured": False,
    }


async def test_system_status_requires_tenant(client: AsyncClient) -> None:
    response = await client.get("/api/v1/system/status")
    assert response.status_code in (400, 401)


async def test_dispatch_queue_reports_configured_backend_not_online(
    client: AsyncClient, create_organization: CreateOrg
) -> None:
    org = await create_organization()

    response = await client.get(
        "/api/v1/dispatch-queues", headers=tenant_headers(org["id"])
    )

    assert response.status_code == 200
    assert response.json()[0]["broker_status"] == "unconfigured"
