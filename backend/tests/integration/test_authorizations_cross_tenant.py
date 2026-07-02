"""Cross-tenant regression tests for authorizations.

Every tenant-scoped resource owned by one organization must be invisible
to another, returning the same 404 contract as a non-existent resource.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import tenant_headers
from tests.integration.test_authorizations_api import _valid_payload

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]


async def _setup_auth_for_tenant(
    client: AsyncClient,
    org_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    """Create a project, verified asset, and submitted authorization."""
    headers = tenant_headers(org_id)
    project = (
        await client.post(
            "/api/v1/projects", json={"name": "Test Project"}, headers=headers
        )
    ).json()
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project["id"],
                "name": "Test Asset",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://api.test.example.com",
                "criticality": "low",
            },
            headers=headers,
        )
    ).json()

    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET status = :status WHERE id = :id"),
            {"status": "verified", "id": asset["id"]},
        )
        await session.commit()

    auth = (
        await client.post(
            f"/api/v1/projects/{project['id']}/authorizations",
            json=_valid_payload(asset["id"]),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)
    return auth["id"], project["id"]


async def test_attacker_cannot_read_victim_authorization(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = await create_organization(name="Victim Org", slug="victim-auth")
    auth_id, _ = await _setup_auth_for_tenant(client, org["id"], session_factory)

    other = await create_organization(name="Attacker Org", slug="attacker-auth")
    attacker_headers = tenant_headers(other["id"])

    response = await client.get(
        f"/api/v1/authorizations/{auth_id}", headers=attacker_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "authorization_not_found"


async def test_attacker_cannot_patch_victim_authorization(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = await create_organization(name="Victim Org", slug="victim-patch")
    auth_id, _ = await _setup_auth_for_tenant(client, org["id"], session_factory)

    other = await create_organization(name="Attacker Org", slug="attacker-patch")
    attacker_headers = tenant_headers(other["id"])

    response = await client.patch(
        f"/api/v1/authorizations/{auth_id}",
        json={"title": "Hijacked"},
        headers=attacker_headers,
    )

    assert response.status_code == 404


async def test_attacker_cannot_submit_victim_authorization(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = await create_organization(name="Victim Org", slug="victim-submit")
    auth_id, _ = await _setup_auth_for_tenant(client, org["id"], session_factory)

    other = await create_organization(name="Attacker Org", slug="attacker-submit")
    attacker_headers = tenant_headers(other["id"])

    # This auth is already submitted; try activating from the attacker tenant.
    response = await client.post(
        f"/api/v1/authorizations/{auth_id}/activate", headers=attacker_headers
    )

    assert response.status_code == 404


async def test_attacker_cannot_create_authorization_in_victim_project(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org = await create_organization(name="Victim Org", slug="victim-proj")
    headers = tenant_headers(org["id"])
    project = (
        await client.post(
            "/api/v1/projects", json={"name": "Vic Project"}, headers=headers
        )
    ).json()

    other = await create_organization(name="Attacker Org", slug="attacker-proj")
    attacker_headers = tenant_headers(other["id"])

    response = await client.post(
        f"/api/v1/projects/{project['id']}/authorizations",
        json=_valid_payload(
            "00000000-0000-0000-0000-000000000001",
            scopes_overrides=[
                {
                    "asset_id": "00000000-0000-0000-0000-000000000001",
                    "allowed_ports": [443],
                    "allowed_paths": "/",
                    "maximum_requests_per_minute": 10,
                    "maximum_concurrency": 1,
                }
            ],
        ),
        headers=attacker_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"
