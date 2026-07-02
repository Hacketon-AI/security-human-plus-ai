"""API/integration tests for engagements."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import tenant_headers

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]

_DOC_SHA256 = "a" * 64
_DOC_NAME = "auth_letter.pdf"


def _valid_auth_payload(asset_id: str) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    return {
        "reference_number": "AUTH-2026-001",
        "title": "Q1 Assessment",
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
        "timezone": "UTC",
        "maximum_risk_tier": "tier_1_safe",
        "production_testing_allowed": False,
        "core_banking_testing_allowed": False,
        "emergency_contact_name": "Officer",
        "emergency_contact_phone": "+1-555-0001",
        "authorization_document_name": _DOC_NAME,
        "authorization_document_sha256": _DOC_SHA256,
        "scopes": [
            {
                "asset_id": asset_id,
                "maximum_requests_per_minute": 60,
                "maximum_concurrency": 5,
            }
        ],
    }


def _valid_engagement_payload(auth_id: str, asset_id: str) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    return {
        "authorization_id": auth_id,
        "name": "Q1 Engagement",
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(days=7)).isoformat(),
        "timezone": "UTC",
        "max_risk_tier": "tier_1_safe",
        "default_rate_limit_per_minute": 30,
        "default_concurrency_limit": 3,
        "emergency_contact_name": "Eng Officer",
        "emergency_contact_email": "eng@example.com",
        "scopes": [
            {
                "asset_id": asset_id,
                "allowed_ports": [443, 8443],
                "allowed_paths": ["/api"],
                "rate_limit_per_minute": 20,
                "concurrency_limit": 2,
            }
        ],
    }


async def _setup_active_auth_and_asset(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, str], str, str, str, str]:
    """Create org → project → verified asset → active authorization."""
    org = await create_organization()
    headers = tenant_headers(org["id"])
    project = (
        await client.post("/api/v1/projects", json={"name": "E"}, headers=headers)
    ).json()
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project["id"],
                "name": "API",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://api.example.com",
                "criticality": "medium",
            },
            headers=headers,
        )
    ).json()

    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET status = :s WHERE id = :id"),
            {"s": "verified", "id": asset["id"]},
        )
        await session.commit()

    auth = (
        await client.post(
            f"/api/v1/projects/{project['id']}/authorizations",
            json=_valid_auth_payload(asset["id"]),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)
    await client.post(f"/api/v1/authorizations/{auth['id']}/activate", headers=headers)
    return headers, org["id"], project["id"], asset["id"], auth["id"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_draft_engagement(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)

    response = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=_valid_engagement_payload(auth_id, asset_id),
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["authorization_id"] == auth_id
    assert len(body["scopes"]) == 1
    assert body["scopes"][0]["allowed_ports"] == [443, 8443]
    assert body["kill_switch_active"] is False


async def test_create_round_trips_sorted_deduped_ports(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    payload = _valid_engagement_payload(auth_id, asset_id)
    payload["scopes"][0]["allowed_ports"] = [8443, 443, 8443, 80]

    response = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    # Normalized identically to AuthorizationScope: sorted and de-duplicated.
    assert response.json()["scopes"][0]["allowed_ports"] == [80, 443, 8443]


async def test_create_accepts_empty_ports_list(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # An explicit empty list is valid: it means "no allowed ports" and overrides
    # the authorization scope rather than inheriting it.
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    payload = _valid_engagement_payload(auth_id, asset_id)
    payload["scopes"][0]["allowed_ports"] = []

    response = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["scopes"][0]["allowed_ports"] == []


async def test_create_omitted_ports_serialize_as_null(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Omitting allowed_ports records None (inherit authorization) and the
    # response contract serializes it as null, not [] — proving list[int] | None.
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    payload = _valid_engagement_payload(auth_id, asset_id)
    del payload["scopes"][0]["allowed_ports"]

    response = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["scopes"][0]["allowed_ports"] is None


@pytest.mark.parametrize(
    "allowed_ports",
    [
        "443,8443",  # free text is not accepted
        ["443"],  # numeric string element
        [443.0],  # float element
        [True],  # bool masquerading as a port
        [0],  # zero is reserved
        [-1],  # negative
        [70000],  # above the valid range
        {"port": 443},  # non-list container
    ],
)
async def test_create_rejects_invalid_allowed_ports(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    allowed_ports: object,
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    payload = _valid_engagement_payload(auth_id, asset_id)
    payload["scopes"][0]["allowed_ports"] = allowed_ports

    response = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422


async def test_create_rejects_inactive_authorization(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    # Revoke the authorization.
    await client.post(
        f"/api/v1/authorizations/{auth_id}/revoke",
        json={"reason": "test"},
        headers=headers,
    )

    response = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=_valid_engagement_payload(auth_id, asset_id),
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "authorization_not_valid_for_engagement"


async def test_create_rejects_unverified_asset(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        _asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    # Create an unverified asset.
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project_id,
                "name": "Draft",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://draft.example.com",
                "criticality": "low",
            },
            headers=headers,
        )
    ).json()

    response = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=_valid_engagement_payload(auth_id, asset["id"]),
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_engagement_scope"


async def test_create_rejects_asset_not_in_auth_scope(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        auth_asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    # Create a second verified asset not added to the authorization scope.
    asset2 = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project_id,
                "name": "Other",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://other.example.com",
                "criticality": "low",
            },
            headers=headers,
        )
    ).json()
    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET status = :s WHERE id = :id"),
            {"s": "verified", "id": asset2["id"]},
        )
        await session.commit()

    # Create an engagement referencing the asset not in auth scope.
    # Schedule validates against authorization scopes.
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, auth_asset_id),
            headers=headers,
        )
    ).json()
    # Swap the scope to the non-authorized asset via update.
    await client.patch(
        f"/api/v1/engagements/{eng['id']}",
        json={
            "scopes": [
                {
                    "asset_id": asset2["id"],
                    "allowed_ports": [443],
                    "rate_limit_per_minute": 10,
                    "concurrency_limit": 1,
                }
            ]
        },
        headers=headers,
    )
    resp = await client.post(
        f"/api/v1/engagements/{eng['id']}/schedule", headers=headers
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_engagement_scope"


async def test_create_rejects_missing_tenant_context(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        _headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)

    # No X-Organization-Id header.
    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=_valid_engagement_payload(auth_id, asset_id),
    )
    assert resp.status_code == 401


async def test_create_rejects_expired_authorization(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    # Force the authorization to expired directly in the database.
    async with session_factory() as session:
        await session.execute(
            text("UPDATE authorizations SET status = :s WHERE id = :id"),
            {"s": "expired", "id": auth_id},
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=_valid_engagement_payload(auth_id, asset_id),
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "authorization_not_valid_for_engagement"


@pytest.mark.parametrize("blocked_status", ["suspended", "retired"])
async def test_create_rejects_suspended_or_retired_asset(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    blocked_status: str,
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    # Force the scope asset to suspended/retired.
    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET status = :s WHERE id = :id"),
            {"s": blocked_status, "id": asset_id},
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=_valid_engagement_payload(auth_id, asset_id),
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_engagement_scope"


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def test_full_lifecycle_draft_to_completed(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)

    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    assert eng["status"] == "draft"

    # Schedule.
    sched = await client.post(
        f"/api/v1/engagements/{eng['id']}/schedule", headers=headers
    )
    assert sched.status_code == 200
    assert sched.json()["status"] == "scheduled"

    # Activate.
    active = await client.post(
        f"/api/v1/engagements/{eng['id']}/activate", headers=headers
    )
    assert active.status_code == 200
    assert active.json()["status"] == "active"
    assert active.json()["activated_at"] is not None

    # Pause.
    paused = await client.post(
        f"/api/v1/engagements/{eng['id']}/pause", headers=headers
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert paused.json()["paused_at"] is not None

    # Resume.
    resumed = await client.post(
        f"/api/v1/engagements/{eng['id']}/resume", headers=headers
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"

    # Complete.
    completed = await client.post(
        f"/api/v1/engagements/{eng['id']}/complete", headers=headers
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None


async def test_cancel_from_draft(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()

    resp = await client.post(f"/api/v1/engagements/{eng['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_cancel_from_scheduled(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/schedule", headers=headers)

    resp = await client.post(f"/api/v1/engagements/{eng['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_cancel_from_paused(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/schedule", headers=headers)
    await client.post(f"/api/v1/engagements/{eng['id']}/activate", headers=headers)
    await client.post(f"/api/v1/engagements/{eng['id']}/pause", headers=headers)

    resp = await client.post(f"/api/v1/engagements/{eng['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


async def test_cannot_activate_draft(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/engagements/{eng['id']}/activate", headers=headers
    )
    assert resp.status_code == 409


async def test_cannot_complete_paused(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/schedule", headers=headers)
    await client.post(f"/api/v1/engagements/{eng['id']}/activate", headers=headers)
    await client.post(f"/api/v1/engagements/{eng['id']}/pause", headers=headers)

    resp = await client.post(
        f"/api/v1/engagements/{eng['id']}/complete", headers=headers
    )
    assert resp.status_code == 409


async def test_completed_is_terminal(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/schedule", headers=headers)
    await client.post(f"/api/v1/engagements/{eng['id']}/activate", headers=headers)
    await client.post(f"/api/v1/engagements/{eng['id']}/complete", headers=headers)

    resp = await client.post(f"/api/v1/engagements/{eng['id']}/pause", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_engagement_state_transition"


async def test_cancelled_is_terminal(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/cancel", headers=headers)

    # Cannot update.
    resp = await client.patch(
        f"/api/v1/engagements/{eng['id']}",
        json={"name": "nope"},
        headers=headers,
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Authorization dependency
# ---------------------------------------------------------------------------


async def test_engagement_risk_tier_must_not_exceed_authorization(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    # Authorization has tier_1_safe; try tier_2_controlled engagement.
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id)
            | {"max_risk_tier": "tier_2_controlled"},
            headers=headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/engagements/{eng['id']}/schedule", headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "authorization_not_valid_for_engagement"


async def test_engagement_window_must_be_inside_auth_window(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    # Authorization window is (now-1day, now+30days). Make the engagement start
    # before the authorization valid_from while keeping duration under 30 days.
    now = datetime.now(tz=UTC)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json={
                **_valid_engagement_payload(auth_id, asset_id),
                "starts_at": (now - timedelta(days=2)).isoformat(),
                "ends_at": (now + timedelta(days=20)).isoformat(),
            },
            headers=headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/engagements/{eng['id']}/schedule", headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "authorization_not_valid_for_engagement"


# ---------------------------------------------------------------------------
# Time range validation
# ---------------------------------------------------------------------------


async def test_ends_at_must_be_after_starts_at(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    now = datetime.now(tz=UTC)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json={
            **_valid_engagement_payload(auth_id, asset_id),
            "starts_at": (now + timedelta(days=5)).isoformat(),
            "ends_at": now.isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 422


async def test_max_30_day_duration(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    now = datetime.now(tz=UTC)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json={
            **_valid_engagement_payload(auth_id, asset_id),
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(days=31)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


async def test_kill_switch_activation(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/schedule", headers=headers)

    resp = await client.post(
        f"/api/v1/engagements/{eng['id']}/kill-switch",
        json={"active": True, "reason": "Emergency stop"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kill_switch_active"] is True
    assert body["kill_switch_reason"] == "Emergency stop"


async def test_kill_switch_blocks_terminal(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/cancel", headers=headers)

    resp = await client.post(
        f"/api/v1/engagements/{eng['id']}/kill-switch",
        json={"active": True, "reason": "Too late"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "kill_switch_immutable"


# ---------------------------------------------------------------------------
# Tenant isolation / cross-tenant
# ---------------------------------------------------------------------------


async def test_cross_tenant_returns_404(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()

    other = await create_organization(name="Other", slug="other-eng")
    attacker = tenant_headers(other["id"])

    assert (
        await client.get(f"/api/v1/engagements/{eng['id']}", headers=attacker)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/engagements/{eng['id']}",
            json={"name": "X"},
            headers=attacker,
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/engagements/{eng['id']}/schedule",
            headers=attacker,
        )
    ).status_code == 404


async def test_organization_id_not_from_body(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers, org_id, project_id, asset_id, auth_id = await _setup_active_auth_and_asset(
        client, create_organization, session_factory
    )
    payload = _valid_engagement_payload(auth_id, asset_id)
    payload["organization_id"] = org_id

    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Concurrent operations
# ---------------------------------------------------------------------------


async def test_concurrent_activation_produces_one_transition(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json=_valid_engagement_payload(auth_id, asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/schedule", headers=headers)

    results = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/engagements/{eng['id']}/activate",
                headers=headers,
            )
            for _ in range(3)
        ]
    )
    active = [r for r in results if r.status_code == 200]
    conflicts = [r for r in results if r.status_code == 409]
    assert len(active) == 1
    assert len(conflicts) == 2

    final = await client.get(f"/api/v1/engagements/{eng['id']}", headers=headers)
    assert final.json()["status"] == "active"


# ---------------------------------------------------------------------------
# Activation timing gate
# ---------------------------------------------------------------------------


async def test_activation_before_starts_at_is_rejected(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    future = datetime.now(tz=UTC) + timedelta(days=5)
    eng = (
        await client.post(
            f"/api/v1/projects/{project_id}/engagements",
            json={
                **_valid_engagement_payload(auth_id, asset_id),
                "starts_at": future.isoformat(),
                "ends_at": (future + timedelta(days=7)).isoformat(),
            },
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/engagements/{eng['id']}/schedule", headers=headers)

    resp = await client.post(
        f"/api/v1/engagements/{eng['id']}/activate", headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "engagement_activation_blocked"


# ---------------------------------------------------------------------------
# Scope required before schedule
# ---------------------------------------------------------------------------


async def test_zero_scopes_rejected_by_pydantic(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json={
            **_valid_engagement_payload(auth_id, asset_id),
            "scopes": [],
        },
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


async def test_list_scoped_by_project(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=_valid_engagement_payload(auth_id, asset_id),
        headers=headers,
    )

    # Create another project.
    other_proj = (
        await client.post("/api/v1/projects", json={"name": "P2"}, headers=headers)
    ).json()

    # List for project_id should include the engagement.
    resp = await client.get(
        f"/api/v1/projects/{project_id}/engagements", headers=headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # List for other project should be empty.
    resp2 = await client.get(
        f"/api/v1/projects/{other_proj['id']}/engagements",
        headers=headers,
    )
    assert resp2.status_code == 200
    assert len(resp2.json()) == 0


# ---------------------------------------------------------------------------
# authorization_scope_id consistency
# ---------------------------------------------------------------------------


async def _authorization_scope_id(
    client: AsyncClient, headers: dict[str, str], auth_id: str
) -> str:
    """Return the id of the linked authorization's first scope."""
    auth = (
        await client.get(f"/api/v1/authorizations/{auth_id}", headers=headers)
    ).json()
    return auth["scopes"][0]["id"]


async def test_engagement_scope_accepts_matching_authorization_scope_id(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)
    scope_id = await _authorization_scope_id(client, headers, auth_id)

    payload = _valid_engagement_payload(auth_id, asset_id)
    payload["scopes"][0]["authorization_scope_id"] = scope_id

    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["scopes"][0]["authorization_scope_id"] == scope_id


async def test_engagement_scope_rejects_scope_from_another_authorization(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)

    # Build a second authorization (same tenant/project/asset) with its own scope.
    other_auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json={
                **_valid_auth_payload(asset_id),
                "reference_number": "AUTH-2026-002",
            },
            headers=headers,
        )
    ).json()
    foreign_scope_id = other_auth["scopes"][0]["id"]

    payload = _valid_engagement_payload(auth_id, asset_id)
    payload["scopes"][0]["authorization_scope_id"] = foreign_scope_id

    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_engagement_scope"


async def test_engagement_scope_rejects_scope_for_another_asset(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    (
        headers,
        _org_id,
        project_id,
        asset_id,
        _auth_id,
    ) = await _setup_active_auth_and_asset(client, create_organization, session_factory)

    # Add a second verified asset and an authorization that scopes both assets.
    asset2 = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project_id,
                "name": "API2",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://api2.example.com",
                "criticality": "low",
            },
            headers=headers,
        )
    ).json()
    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET status = :s WHERE id = :id"),
            {"s": "verified", "id": asset2["id"]},
        )
        await session.commit()

    multi_auth_payload = _valid_auth_payload(asset_id)
    multi_auth_payload["reference_number"] = "AUTH-2026-003"
    multi_auth_payload["scopes"].append(
        {
            "asset_id": asset2["id"],
            "maximum_requests_per_minute": 60,
            "maximum_concurrency": 5,
        }
    )
    multi_auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=multi_auth_payload,
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/authorizations/{multi_auth['id']}/submit", headers=headers
    )
    await client.post(
        f"/api/v1/authorizations/{multi_auth['id']}/activate", headers=headers
    )
    # Find the scope id belonging to asset2.
    scope_for_asset2 = next(
        s["id"] for s in multi_auth["scopes"] if s["asset_id"] == asset2["id"]
    )

    # Engagement scopes asset_id but references the scope that covers asset2.
    payload = _valid_engagement_payload(multi_auth["id"], asset_id)
    payload["scopes"][0]["authorization_scope_id"] = scope_for_asset2

    resp = await client.post(
        f"/api/v1/projects/{project_id}/engagements",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_engagement_scope"
