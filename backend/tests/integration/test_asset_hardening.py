"""Asset mutation-policy enforcement and the injected clock boundary."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from app.modules.assets.enums import VerificationMethod
from app.modules.assets.repository import AssetRepository
from app.modules.assets.schemas import AssetVerificationRequest
from app.modules.assets.service import AssetService
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import FixedClock, tenant_headers


@pytest.fixture
async def registered_asset(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, str]:
    """Register one draft asset; return the tenant, project, and asset ids."""
    organization = await create_organization()
    headers = tenant_headers(organization["id"])
    project = await client.post(
        "/api/v1/projects", json={"name": "Estate"}, headers=headers
    )
    asset = await client.post(
        "/api/v1/assets",
        json={
            "project_id": project.json()["id"],
            "name": "Site",
            "asset_type": "web_application",
            "environment": "production",
            "target": "https://www.example.com",
            "criticality": "high",
        },
        headers=headers,
    )
    return {
        "organization_id": organization["id"],
        "project_id": project.json()["id"],
        "asset_id": asset.json()["id"],
    }


@pytest.mark.parametrize("protected_status", ["suspended", "retired"])
async def test_patch_is_rejected_for_protected_states(
    client: AsyncClient,
    registered_asset: dict[str, str],
    set_asset_status: Callable[[str, str], Awaitable[None]],
    protected_status: str,
) -> None:
    await set_asset_status(registered_asset["asset_id"], protected_status)

    response = await client.patch(
        f"/api/v1/assets/{registered_asset['asset_id']}",
        json={"name": "Renamed"},
        headers=tenant_headers(registered_asset["organization_id"]),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "asset_mutation_not_allowed"


@pytest.mark.parametrize("mutable_status", ["pending_verification", "verified"])
async def test_patch_allows_metadata_in_mutable_states(
    client: AsyncClient,
    registered_asset: dict[str, str],
    set_asset_status: Callable[[str, str], Awaitable[None]],
    mutable_status: str,
) -> None:
    await set_asset_status(registered_asset["asset_id"], mutable_status)

    response = await client.patch(
        f"/api/v1/assets/{registered_asset['asset_id']}",
        json={"name": "Renamed", "criticality": "critical"},
        headers=tenant_headers(registered_asset["organization_id"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["criticality"] == "critical"


async def test_request_verification_uses_injected_clock(
    registered_asset: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    tenant = TenantContext(UUID(registered_asset["organization_id"]))

    async with session_factory() as session:
        service = AssetService(
            AssetRepository(session),
            ProjectRepository(session),
            FixedClock(moment),
        )
        asset = await service.request_verification(
            UUID(registered_asset["asset_id"]),
            tenant,
            AssetVerificationRequest(method=VerificationMethod.dns_txt_record),
        )
        await session.commit()

    assert asset.verification_requested_at == moment
