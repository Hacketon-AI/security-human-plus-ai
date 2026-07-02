"""API tests for the assets endpoints."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from tests.conftest import tenant_headers


@pytest.fixture
async def tenant_with_project(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, str]:
    """Create an organization with one active project; return their ids."""
    organization = await create_organization()
    project = await client.post(
        "/api/v1/projects",
        json={"name": "Web Estate"},
        headers=tenant_headers(organization["id"]),
    )
    assert project.status_code == 201, project.text
    return {
        "organization_id": organization["id"],
        "project_id": project.json()["id"],
    }


def _asset_body(project_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "project_id": project_id,
        "name": "Marketing Site",
        "asset_type": "web_application",
        "environment": "production",
        "target": "https://www.example.com",
        "criticality": "high",
    }
    body.update(overrides)
    return body


async def test_register_asset_is_draft_with_normalized_target(
    client: AsyncClient, tenant_with_project: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/assets",
        json=_asset_body(
            tenant_with_project["project_id"], target="HTTPS://WWW.Example.com/"
        ),
        headers=tenant_headers(tenant_with_project["organization_id"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["target"] == "https://www.example.com/"
    assert body["organization_id"] == tenant_with_project["organization_id"]
    assert body["ownership_verified_at"] is None


async def test_register_asset_rejects_plain_http_target(
    client: AsyncClient, tenant_with_project: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/assets",
        json=_asset_body(
            tenant_with_project["project_id"], target="http://www.example.com"
        ),
        headers=tenant_headers(tenant_with_project["organization_id"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_asset_target"


async def test_register_asset_cannot_set_status_directly(
    client: AsyncClient, tenant_with_project: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/assets",
        json=_asset_body(tenant_with_project["project_id"], status="verified"),
        headers=tenant_headers(tenant_with_project["organization_id"]),
    )

    assert response.status_code == 422


async def test_register_asset_on_suspended_project_is_rejected(
    client: AsyncClient,
    tenant_with_project: dict[str, str],
    set_project_status: Callable[[str, str], Awaitable[None]],
) -> None:
    await set_project_status(tenant_with_project["project_id"], "suspended")

    response = await client.post(
        "/api/v1/assets",
        json=_asset_body(tenant_with_project["project_id"]),
        headers=tenant_headers(tenant_with_project["organization_id"]),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "project_not_accepting_assets"


async def test_patch_asset_updates_metadata(
    client: AsyncClient, tenant_with_project: dict[str, str]
) -> None:
    headers = tenant_headers(tenant_with_project["organization_id"])
    created = await client.post(
        "/api/v1/assets",
        json=_asset_body(tenant_with_project["project_id"]),
        headers=headers,
    )
    asset = created.json()

    response = await client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"name": "Renamed Site", "criticality": "critical"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed Site"
    assert body["criticality"] == "critical"
    assert body["updated_at"] >= body["created_at"]


async def test_request_verification_moves_draft_to_pending(
    client: AsyncClient, tenant_with_project: dict[str, str]
) -> None:
    headers = tenant_headers(tenant_with_project["organization_id"])
    created = await client.post(
        "/api/v1/assets",
        json=_asset_body(tenant_with_project["project_id"]),
        headers=headers,
    )
    asset = created.json()

    response = await client.post(
        f"/api/v1/assets/{asset['id']}/request-verification",
        json={"method": "dns_txt_record"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_verification"
    assert body["verification_method"] == "dns_txt_record"
    assert body["verification_requested_at"] is not None
    # Not auto-verified: ownership proof is a separate stage.
    assert body["ownership_verified_at"] is None


async def test_request_verification_twice_is_invalid_transition(
    client: AsyncClient, tenant_with_project: dict[str, str]
) -> None:
    headers = tenant_headers(tenant_with_project["organization_id"])
    created = await client.post(
        "/api/v1/assets",
        json=_asset_body(tenant_with_project["project_id"]),
        headers=headers,
    )
    asset_id = created.json()["id"]
    await client.post(
        f"/api/v1/assets/{asset_id}/request-verification",
        json={"method": "dns_txt_record"},
        headers=headers,
    )

    second = await client.post(
        f"/api/v1/assets/{asset_id}/request-verification",
        json={"method": "http_file"},
        headers=headers,
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "invalid_asset_state_transition"


async def test_list_assets_filters_by_project(
    client: AsyncClient, tenant_with_project: dict[str, str]
) -> None:
    headers = tenant_headers(tenant_with_project["organization_id"])
    await client.post(
        "/api/v1/assets",
        json=_asset_body(tenant_with_project["project_id"]),
        headers=headers,
    )

    matching = await client.get(
        "/api/v1/assets",
        params={"project_id": tenant_with_project["project_id"]},
        headers=headers,
    )
    assert matching.status_code == 200
    assert len(matching.json()) == 1
