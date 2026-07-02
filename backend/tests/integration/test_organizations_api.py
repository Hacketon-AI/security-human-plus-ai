"""API tests for the organizations endpoints."""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from httpx import AsyncClient
from tests.conftest import tenant_headers


async def test_create_organization_starts_active_with_derived_slug(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/organizations", json={"name": "Acme Bank"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Acme Bank"
    assert body["slug"] == "acme-bank"
    assert body["status"] == "active"


async def test_create_organization_rejects_duplicate_slug(
    client: AsyncClient,
) -> None:
    await client.post("/api/v1/organizations", json={"name": "Acme", "slug": "acme"})
    response = await client.post(
        "/api/v1/organizations", json={"name": "Acme Two", "slug": "acme"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "organization_slug_conflict"


async def test_get_own_organization(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    organization = await create_organization()
    response = await client.get(
        f"/api/v1/organizations/{organization['id']}",
        headers=tenant_headers(organization["id"]),
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization["id"]


async def test_get_organization_requires_tenant_context(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    organization = await create_organization()
    response = await client.get(f"/api/v1/organizations/{organization['id']}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "tenant_context_missing"


async def test_get_other_tenant_organization_is_not_found(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    organization = await create_organization()
    # A different, unrelated tenant context must not see this organization, and
    # the contract must match a genuinely missing resource.
    response = await client.get(
        f"/api/v1/organizations/{organization['id']}",
        headers=tenant_headers(uuid4()),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "organization_not_found"
