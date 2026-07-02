"""API tests for the projects endpoints."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from tests.conftest import tenant_headers


async def test_create_project_under_tenant(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    organization = await create_organization()
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Mobile Banking", "description": "iOS and Android apps"},
        headers=tenant_headers(organization["id"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["organization_id"] == organization["id"]
    assert body["slug"] == "mobile-banking"
    assert body["status"] == "active"


async def test_project_body_cannot_assert_organization_id(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    organization = await create_organization()
    # A client-supplied organization_id must be rejected at the edge, not
    # trusted as ownership.
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Sneaky", "organization_id": organization["id"]},
        headers=tenant_headers(organization["id"]),
    )

    assert response.status_code == 422


async def test_create_project_requires_tenant_context(client: AsyncClient) -> None:
    response = await client.post("/api/v1/projects", json={"name": "Orphan"})

    assert response.status_code == 401


async def test_archived_organization_rejects_new_projects(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
    set_organization_status: Callable[[str, str], Awaitable[None]],
) -> None:
    organization = await create_organization()
    await set_organization_status(organization["id"], "archived")

    response = await client.post(
        "/api/v1/projects",
        json={"name": "Too Late"},
        headers=tenant_headers(organization["id"]),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "organization_not_accepting_projects"


async def test_duplicate_slug_within_org_conflicts_but_not_across_orgs(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    org_a = await create_organization(name="Org A", slug="org-a")
    org_b = await create_organization(name="Org B", slug="org-b")

    first = await client.post(
        "/api/v1/projects",
        json={"name": "Core", "slug": "core"},
        headers=tenant_headers(org_a["id"]),
    )
    assert first.status_code == 201

    duplicate = await client.post(
        "/api/v1/projects",
        json={"name": "Core Again", "slug": "core"},
        headers=tenant_headers(org_a["id"]),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "project_slug_conflict"

    # Same slug under a different tenant is fine: slugs are per-organization.
    other_tenant = await client.post(
        "/api/v1/projects",
        json={"name": "Core", "slug": "core"},
        headers=tenant_headers(org_b["id"]),
    )
    assert other_tenant.status_code == 201


async def test_list_projects_is_scoped_to_tenant(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    org_a = await create_organization(name="Org A", slug="org-a")
    org_b = await create_organization(name="Org B", slug="org-b")
    await client.post(
        "/api/v1/projects",
        json={"name": "A Project"},
        headers=tenant_headers(org_a["id"]),
    )

    listed = await client.get("/api/v1/projects", headers=tenant_headers(org_b["id"]))
    assert listed.status_code == 200
    assert listed.json() == []
