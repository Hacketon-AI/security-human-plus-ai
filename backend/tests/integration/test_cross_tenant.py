"""Cross-tenant regression tests.

Every tenant-scoped resource owned by one organization must be invisible to
another, returning the same 404 contract as a non-existent resource. A valid
resource UUID is never proof of authorization.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from tests.conftest import tenant_headers


@pytest.fixture
async def victim_and_attacker(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, str]:
    """Two tenants; the victim owns a project and an asset."""
    victim = await create_organization(name="Victim Org", slug="victim")
    attacker = await create_organization(name="Attacker Org", slug="attacker")

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Victim Project"},
        headers=tenant_headers(victim["id"]),
    )
    asset = await client.post(
        "/api/v1/assets",
        json={
            "project_id": project.json()["id"],
            "name": "Victim Asset",
            "asset_type": "api",
            "environment": "production",
            "target": "https://api.victim.example.com",
            "criticality": "critical",
        },
        headers=tenant_headers(victim["id"]),
    )
    return {
        "attacker_id": attacker["id"],
        "project_id": project.json()["id"],
        "asset_id": asset.json()["id"],
    }


async def test_attacker_cannot_read_victim_project(
    client: AsyncClient, victim_and_attacker: dict[str, str]
) -> None:
    response = await client.get(
        f"/api/v1/projects/{victim_and_attacker['project_id']}",
        headers=tenant_headers(victim_and_attacker["attacker_id"]),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"


async def test_attacker_cannot_read_victim_asset(
    client: AsyncClient, victim_and_attacker: dict[str, str]
) -> None:
    response = await client.get(
        f"/api/v1/assets/{victim_and_attacker['asset_id']}",
        headers=tenant_headers(victim_and_attacker["attacker_id"]),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "asset_not_found"


async def test_attacker_cannot_patch_victim_asset(
    client: AsyncClient, victim_and_attacker: dict[str, str]
) -> None:
    response = await client.patch(
        f"/api/v1/assets/{victim_and_attacker['asset_id']}",
        json={"name": "Hijacked"},
        headers=tenant_headers(victim_and_attacker["attacker_id"]),
    )
    assert response.status_code == 404


async def test_attacker_cannot_request_verification_on_victim_asset(
    client: AsyncClient, victim_and_attacker: dict[str, str]
) -> None:
    response = await client.post(
        f"/api/v1/assets/{victim_and_attacker['asset_id']}/request-verification",
        json={"method": "dns_txt_record"},
        headers=tenant_headers(victim_and_attacker["attacker_id"]),
    )
    assert response.status_code == 404


async def test_attacker_cannot_register_asset_in_victim_project(
    client: AsyncClient, victim_and_attacker: dict[str, str]
) -> None:
    # Targeting the victim's project id from the attacker's tenant must look
    # like the project does not exist.
    response = await client.post(
        "/api/v1/assets",
        json={
            "project_id": victim_and_attacker["project_id"],
            "name": "Foothold",
            "asset_type": "web_application",
            "environment": "production",
            "target": "https://foothold.example.com",
            "criticality": "low",
        },
        headers=tenant_headers(victim_and_attacker["attacker_id"]),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"
