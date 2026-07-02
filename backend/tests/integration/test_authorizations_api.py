"""API/integration tests for authorizations."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import FixedClock, tenant_headers

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]

_DOC_SHA256 = hashlib.sha256(b"test-document-content").hexdigest()
_DOC_NAME = "authorization_letter_v1.pdf"


def _valid_payload(
    asset_id: str,
    *,
    overrides: dict[str, Any] | None = None,
    scopes_overrides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    base: dict[str, Any] = {
        "reference_number": "AUTH-2026-001",
        "title": "Q1 Security Assessment",
        "description": "Authorized security testing for Q1",
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
        "timezone": "Asia/Jakarta",
        "maximum_risk_tier": "tier_1_safe",
        "production_testing_allowed": False,
        "core_banking_testing_allowed": False,
        "emergency_contact_name": "Security Officer",
        "emergency_contact_phone": "+62-811-1111-1111",
        "authorization_document_name": _DOC_NAME,
        "authorization_document_sha256": _DOC_SHA256,
        "authorization_document_reference": "ref://docs/2026/auth-001",
        "scopes": scopes_overrides
        or [
            {
                "asset_id": asset_id,
                "allowed_ports": [443, 8443],
                "allowed_paths": "/api,/admin",
                "excluded_paths": "/admin/secret",
                "maximum_requests_per_minute": 60,
                "maximum_concurrency": 5,
                "notes": "Primary API scope",
            }
        ],
    }
    if overrides:
        base.update(overrides)
    return base


async def _create_verified_asset(
    client: AsyncClient, create_organization: CreateOrg
) -> tuple[dict[str, Any], dict[str, str], str, str]:
    """Create verified asset; returns (org, headers, project_id, asset_id)."""
    org = await create_organization()
    headers = tenant_headers(org["id"])
    project = (
        await client.post(
            "/api/v1/projects", json={"name": "Q1 Platform"}, headers=headers
        )
    ).json()
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project["id"],
                "name": "API Gateway",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://api.staging.example.com",
                "criticality": "medium",
            },
            headers=headers,
        )
    ).json()

    # Request verification, then verify via a challenge.
    await client.post(
        f"/api/v1/assets/{asset['id']}/request-verification",
        json={"method": "dns_txt_record"},
        headers=headers,
    )
    challenge = (
        await client.post(
            f"/api/v1/assets/{asset['id']}/verification-challenges",
            headers=headers,
        )
    ).json()
    # Direct DB update to mark asset verified (bypass DNS resolution).
    return org, headers, project["id"], asset["id"], challenge


async def _verified_asset(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, Any], dict[str, str], str, str]:
    org = await create_organization()
    headers = tenant_headers(org["id"])
    project = (
        await client.post(
            "/api/v1/projects", json={"name": "Q1 Platform"}, headers=headers
        )
    ).json()
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project["id"],
                "name": "API Gateway",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://api.staging.example.com",
                "criticality": "medium",
            },
            headers=headers,
        )
    ).json()

    # Direct status update to verified.
    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET status = :status WHERE id = :id"),
            {"status": "verified", "id": asset["id"]},
        )
        await session.commit()

    return org, headers, project["id"], asset["id"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_with_verified_asset_returns_201(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    payload = _valid_payload(asset_id)

    response = await client.post(
        f"/api/v1/projects/{project_id}/authorizations",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["reference_number"] == "AUTH-2026-001"
    assert body["title"] == "Q1 Security Assessment"
    assert len(body["scopes"]) == 1
    assert body["scopes"][0]["asset_id"] == asset_id
    # allowed_ports round-trips as a structured, sorted list[int] — never text.
    assert body["scopes"][0]["allowed_ports"] == [443, 8443]
    # SHA-256 is visible in response (not a secret).
    assert body["authorization_document_sha256"] == _DOC_SHA256


@pytest.mark.parametrize(
    "allowed_ports",
    [
        "443,8443",  # free text is no longer accepted
        ["443"],  # numeric string element
        [443.0],  # float element
        [True],  # bool masquerading as a port
        [0],  # zero is reserved
        [-1],  # negative
        [70000],  # above the valid range
    ],
)
async def test_create_rejects_invalid_allowed_ports(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    allowed_ports: object,
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    payload = _valid_payload(
        asset_id,
        scopes_overrides=[
            {
                "asset_id": asset_id,
                "allowed_ports": allowed_ports,
                "maximum_requests_per_minute": 60,
                "maximum_concurrency": 5,
            }
        ],
    )

    response = await client.post(
        f"/api/v1/projects/{project_id}/authorizations",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422


async def test_create_rejects_unverified_asset(
    client: AsyncClient,
    create_organization: CreateOrg,
) -> None:
    org = await create_organization()
    headers = tenant_headers(org["id"])
    project = (
        await client.post("/api/v1/projects", json={"name": "P"}, headers=headers)
    ).json()
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project["id"],
                "name": "Draft Asset",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://api.example.com",
                "criticality": "low",
            },
            headers=headers,
        )
    ).json()

    payload = _valid_payload(asset["id"])
    response = await client.post(
        f"/api/v1/projects/{project['id']}/authorizations",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_authorization_scope"


async def test_create_rejects_foreign_project_asset(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, _project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    # Create a second project.
    other_project = (
        await client.post("/api/v1/projects", json={"name": "Other"}, headers=headers)
    ).json()

    # Use the asset belonging to project_id against other_project.
    payload = _valid_payload(asset_id)
    response = await client.post(
        f"/api/v1/projects/{other_project['id']}/authorizations",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_authorization_scope"


async def test_create_rejects_zero_scopes(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    payload = _valid_payload(asset_id, overrides={"scopes": []})

    response = await client.post(
        f"/api/v1/projects/{project_id}/authorizations",
        json=payload,
        headers=headers,
    )

    # Pydantic rejects min_length=1 at the edge.
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Time range validation
# ---------------------------------------------------------------------------


async def test_create_rejects_invalid_time_range(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    now = datetime.now(tz=UTC)
    payload = _valid_payload(
        asset_id,
        overrides={
            "valid_from": (now + timedelta(days=10)).isoformat(),
            "valid_until": now.isoformat(),
        },
    )

    response = await client.post(
        f"/api/v1/projects/{project_id}/authorizations",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_authorization_time_range"


async def test_create_rejects_over_90_day_validity(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    now = datetime.now(tz=UTC)
    payload = _valid_payload(
        asset_id,
        overrides={
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=91)).isoformat(),
        },
    )

    response = await client.post(
        f"/api/v1/projects/{project_id}/authorizations",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_authorization_time_range"


# ---------------------------------------------------------------------------
# Draft update
# ---------------------------------------------------------------------------


async def test_draft_can_be_updated(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()

    response = await client.patch(
        f"/api/v1/authorizations/{auth['id']}",
        json={"title": "Updated Title", "description": "Revised scope"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated Title"
    assert body["description"] == "Revised scope"
    assert body["status"] == "draft"


async def test_submitted_authorization_is_immutable(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)

    response = await client.patch(
        f"/api/v1/authorizations/{auth['id']}",
        json={"title": "Should Fail"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "authorization_immutable"


# ---------------------------------------------------------------------------
# State transitions: happy path
# ---------------------------------------------------------------------------


async def test_full_happy_path_draft_to_active(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )

    # Create draft.
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()
    assert auth["status"] == "draft"

    # Submit.
    submitted = await client.post(
        f"/api/v1/authorizations/{auth['id']}/submit", headers=headers
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["submitted_at"] is not None

    # Activate.
    activated = await client.post(
        f"/api/v1/authorizations/{auth['id']}/activate", headers=headers
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert activated.json()["activated_at"] is not None

    # Revoke.
    revoked = await client.post(
        f"/api/v1/authorizations/{auth['id']}/revoke",
        json={"reason": "Project scope changed"},
        headers=headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["revocation_reason"] == "Project scope changed"


async def test_submitted_can_be_rejected(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)

    rejected = await client.post(
        f"/api/v1/authorizations/{auth['id']}/reject",
        json={"reason": "Incomplete scope definition"},
        headers=headers,
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Incomplete scope definition"


# ---------------------------------------------------------------------------
# Invalid state transitions
# ---------------------------------------------------------------------------


async def test_cannot_activate_draft(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/activate", headers=headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_authorization_state_transition"


async def test_cannot_submit_active(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)
    await client.post(f"/api/v1/authorizations/{auth['id']}/activate", headers=headers)

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/submit", headers=headers
    )

    assert response.status_code == 409


async def test_cannot_revoke_draft(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/revoke",
        json={"reason": "test"},
        headers=headers,
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Risk tier and core banking gates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier", ["tier_2_controlled", "tier_3_critical"])
async def test_tier_2_and_3_activation_is_blocked(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    tier: str,
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id, overrides={"maximum_risk_tier": tier}),
            headers=headers,
        )
    ).json()

    # Submit should be blocked because tier validation runs at submit.
    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/submit", headers=headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "authorization_activation_blocked"


async def test_core_banking_flag_is_rejected(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(
                asset_id, overrides={"core_banking_testing_allowed": True}
            ),
            headers=headers,
        )
    ).json()

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/submit", headers=headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "authorization_activation_blocked"


# ---------------------------------------------------------------------------
# Production restrictions
# ---------------------------------------------------------------------------


async def test_production_asset_restricts_risk_tier(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    # Change the asset environment to production.
    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET environment = :env WHERE id = :id"),
            {"env": "production", "id": asset_id},
        )
        await session.commit()

    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(
                asset_id,
                overrides={
                    "maximum_risk_tier": "tier_1_safe",
                    "production_testing_allowed": True,
                },
            ),
            headers=headers,
        )
    ).json()

    # tier_1_safe with production is allowed.
    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/submit", headers=headers
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Document metadata
# ---------------------------------------------------------------------------


async def test_incomplete_document_metadata_is_rejected_on_submit(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    # Create with valid document metadata, then clear the name via direct
    # DB update to bypass Pydantic edge validation.
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()

    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE authorizations SET authorization_document_name = '' "
                "WHERE id = :id"
            ),
            {"id": auth["id"]},
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/submit", headers=headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "authorization_activation_blocked"


async def test_non_hex_sha256_is_rejected_on_submit(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """SHA-256 must be lowercase hex even if bypassing Pydantic edge validation."""
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()

    # Direct DB update to inject a non-hex SHA-256.
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE authorizations "
                "SET authorization_document_sha256 = :v WHERE id = :id"
            ),
            {"v": "z" * 64, "id": auth["id"]},
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/submit", headers=headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "authorization_activation_blocked"


# ---------------------------------------------------------------------------
# Automatic expiry
# ---------------------------------------------------------------------------


async def test_active_authorization_auto_expires(
    verification_app: Any,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """When an active authorization's valid_until is in the past, the GET
    endpoint transitions it to expired."""
    v_client, _resolver, app = verification_app
    from app.platform.clock import get_clock

    # Clock set to a date well within the validity window.
    now = datetime(2026, 1, 15, tzinfo=UTC)
    app.dependency_overrides[get_clock] = lambda: FixedClock(now)

    _org, headers, project_id, asset_id = await _verified_asset(
        v_client, create_organization, session_factory
    )
    payload = _valid_payload(
        asset_id,
        overrides={
            "valid_from": (now - timedelta(days=1)).isoformat(),
            "valid_until": (now + timedelta(days=30)).isoformat(),
        },
    )

    auth = (
        await v_client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=payload,
            headers=headers,
        )
    ).json()
    await v_client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)
    await v_client.post(
        f"/api/v1/authorizations/{auth['id']}/activate", headers=headers
    )

    # Still active before expiry.
    get_response = await v_client.get(
        f"/api/v1/authorizations/{auth['id']}", headers=headers
    )
    assert get_response.json()["status"] == "active"

    # Advance the clock past valid_until. The next GET should auto-expire.
    expired_moment = now + timedelta(days=60)
    app.dependency_overrides[get_clock] = lambda: FixedClock(expired_moment)
    expired_response = await v_client.get(
        f"/api/v1/authorizations/{auth['id']}", headers=headers
    )
    assert expired_response.json()["status"] == "expired"


# ---------------------------------------------------------------------------
# Activation timing gates
# ---------------------------------------------------------------------------


async def test_activation_before_valid_from_is_rejected(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:

    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    future = datetime(2027, 1, 1, tzinfo=UTC)
    payload = _valid_payload(
        asset_id,
        overrides={
            "valid_from": future.isoformat(),
            "valid_until": (future + timedelta(days=30)).isoformat(),
        },
    )

    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=payload,
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/activate", headers=headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "authorization_activation_blocked"


# ---------------------------------------------------------------------------
# Concurrent activation
# ---------------------------------------------------------------------------


async def test_concurrent_activation_produces_one_transition(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)

    results = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/authorizations/{auth['id']}/activate", headers=headers
            )
            for _ in range(3)
        ]
    )

    [r.status_code for r in results]
    active_responses = [r for r in results if r.status_code == 200]
    conflict_responses = [r for r in results if r.status_code == 409]

    assert len(active_responses) == 1, (
        f"Expected 1 success, got {len(active_responses)}"
    )
    assert len(conflict_responses) == 2, (
        f"Expected 2 conflicts, got {len(conflict_responses)}"
    )
    assert all(r.json()["status"] == "active" for r in active_responses)

    # Database should show exactly one active row.
    get_response = await client.get(
        f"/api/v1/authorizations/{auth['id']}", headers=headers
    )
    assert get_response.json()["status"] == "active"


# ---------------------------------------------------------------------------
# Submit/update race
# ---------------------------------------------------------------------------


async def test_submit_update_race_is_handled(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Race submit against a same-asset scope update.

    Both operations lock the authorization row, so they serialize on it. Two
    outcomes are valid and each must stay consistent — never a raw IntegrityError
    or 500, and never a silently lost mutation:

    * submit wins the lock → it transitions to ``submitted`` (200) and the later
      PATCH is rejected as immutable (409); the original scopes are preserved.
    * the PATCH wins the lock → it replaces the scopes (200), then submit
      validates and submits the *updated* scopes (200).

    The PATCH reuses the same ``asset_id`` as the existing scope, exercising the
    ``(authorization_id, asset_id)`` unique constraint during scope replacement —
    the exact path that previously leaked a transient unique violation.
    """
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )

    # Repeat: which side wins the row lock is timing-dependent, so a single run
    # only exercises one branch. A fresh authorization is raced each iteration
    # (a submitted authorization can no longer be raced).
    for _ in range(6):
        auth = (
            await client.post(
                f"/api/v1/projects/{project_id}/authorizations",
                json=_valid_payload(asset_id),
                headers=headers,
            )
        ).json()

        submit_resp, patch_resp = await asyncio.gather(
            client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers),
            client.patch(
                f"/api/v1/authorizations/{auth['id']}",
                json={
                    "scopes": [
                        {
                            "asset_id": asset_id,
                            "allowed_ports": [8443],
                            "maximum_requests_per_minute": 30,
                            "maximum_concurrency": 2,
                        }
                    ]
                },
                headers=headers,
            ),
        )

        # No raw IntegrityError / 500 ever surfaces; only typed outcomes.
        assert submit_resp.status_code == 200, submit_resp.text
        assert patch_resp.status_code in (200, 409), patch_resp.text

        final = (
            await client.get(f"/api/v1/authorizations/{auth['id']}", headers=headers)
        ).json()
        # The final state is submitted regardless of who won the lock.
        assert final["status"] == "submitted"
        assert len(final["scopes"]) == 1
        final_ports = final["scopes"][0]["allowed_ports"]

        if patch_resp.status_code == 200:
            # The update won the lock: submit validated and froze the new scopes.
            assert final_ports == [8443]
        else:
            # Submit won the lock: the update was rejected, original scopes kept.
            assert final_ports == [443, 8443]


# ---------------------------------------------------------------------------
# Revoke after submit
# ---------------------------------------------------------------------------


async def test_cannot_revoke_submitted(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/revoke",
        json={"reason": "test"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_authorization_state_transition"


# ---------------------------------------------------------------------------
# Organization_id not from body
# ---------------------------------------------------------------------------


async def test_organization_id_in_body_is_rejected(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    payload = _valid_payload(asset_id)
    payload["organization_id"] = str(org["id"])

    response = await client.post(
        f"/api/v1/projects/{project_id}/authorizations",
        json=payload,
        headers=headers,
    )

    # extra="forbid" rejects unknown fields.
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Document reference is not read as a filesystem path
# ---------------------------------------------------------------------------


async def test_document_reference_is_opaque(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The document reference must be stored as-is and never interpreted
    as a filesystem path. Even references that look like absolute paths
    must be accepted and stored opaquely."""
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    payload = _valid_payload(
        asset_id,
        overrides={"authorization_document_reference": "/etc/passwd"},
    )

    response = await client.post(
        f"/api/v1/projects/{project_id}/authorizations",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    # The value is stored exactly as provided.
    assert response.json()["authorization_document_reference"] == "/etc/passwd"


# ---------------------------------------------------------------------------
# No sensitive document metadata in error responses
# ---------------------------------------------------------------------------


async def test_document_sha256_not_in_error_messages(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(
                asset_id,
                overrides={"authorization_document_sha256": "0" * 64},
            ),
            headers=headers,
        )
    ).json()
    # Clear the document name via direct DB to bypass Pydantic validation.
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE authorizations SET authorization_document_name = '' "
                "WHERE id = :id"
            ),
            {"id": auth["id"]},
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/submit", headers=headers
    )

    body = response.json()
    assert response.status_code == 422
    assert _DOC_SHA256 not in body["error"]["message"]
    # SHA-256 is never in error messages for failed transitions.
    assert body["error"]["code"] == "authorization_activation_blocked"


# ---------------------------------------------------------------------------
# Production activation guard
# ---------------------------------------------------------------------------


async def test_activation_endpoint_is_available_in_development(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """In development, activation succeeds (provisioning dependency is active)."""
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)

    response = await client.post(
        f"/api/v1/authorizations/{auth['id']}/activate", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"


async def test_replace_scopes_persists_new_scope_set(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regression: updating a draft authorization's scopes must replace the
    scope rows with correctly anchored FKs and drop the old ones."""
    _org, headers, project_id, asset_id = await _verified_asset(
        client, create_organization, session_factory
    )
    # A second verified asset to swap the scope to.
    asset2 = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project_id,
                "name": "Second API",
                "asset_type": "api",
                "environment": "staging",
                "target": "https://api2.staging.example.com",
                "criticality": "low",
            },
            headers=headers,
        )
    ).json()
    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET status = :status WHERE id = :id"),
            {"status": "verified", "id": asset2["id"]},
        )
        await session.commit()

    auth = (
        await client.post(
            f"/api/v1/projects/{project_id}/authorizations",
            json=_valid_payload(asset_id),
            headers=headers,
        )
    ).json()
    original_scope_id = auth["scopes"][0]["id"]

    # Replace the scope set with a scope referencing the second asset.
    updated = await client.patch(
        f"/api/v1/authorizations/{auth['id']}",
        json={
            "scopes": [
                {
                    "asset_id": asset2["id"],
                    "maximum_requests_per_minute": 10,
                    "maximum_concurrency": 1,
                }
            ]
        },
        headers=headers,
    )

    assert updated.status_code == 200
    body = updated.json()
    assert len(body["scopes"]) == 1
    assert body["scopes"][0]["asset_id"] == asset2["id"]
    # The new scope is a fresh row anchored to the authorization.
    assert body["scopes"][0]["id"] != original_scope_id

    # Fetching again confirms the persisted state (FK populated, old row gone).
    refetched = (
        await client.get(f"/api/v1/authorizations/{auth['id']}", headers=headers)
    ).json()
    assert len(refetched["scopes"]) == 1
    assert refetched["scopes"][0]["asset_id"] == asset2["id"]
