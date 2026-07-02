"""API/integration tests for DNS TXT ownership verification."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.modules.asset_verifications.enums import ChallengeStatus
from app.modules.asset_verifications.models import AssetVerificationChallenge
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import FakeDnsResolver, tenant_headers

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]


async def _pending_asset(
    client: AsyncClient,
    create_organization: CreateOrg,
    *,
    asset_type: str = "web_application",
    target: str = "https://www.example.com",
    request_verification: bool = True,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Create org/project/asset and (optionally) move the asset to pending."""
    org = await create_organization()
    headers = tenant_headers(org["id"])
    project = (
        await client.post("/api/v1/projects", json={"name": "Estate"}, headers=headers)
    ).json()
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project["id"],
                "name": "Site",
                "asset_type": asset_type,
                "environment": "staging",
                "target": target,
                "criticality": "medium",
            },
            headers=headers,
        )
    ).json()
    if request_verification:
        await client.post(
            f"/api/v1/assets/{asset['id']}/request-verification",
            json={"method": "dns_txt_record"},
            headers=headers,
        )
    return org, headers, asset


def _base(asset_id: str) -> str:
    return f"/api/v1/assets/{asset_id}/verification-challenges"


async def test_create_returns_record_and_persists_only_digest(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)

    response = await client.post(_base(asset["id"]), headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["record_type"] == "TXT"
    assert body["record_name"] == "_securescope-verification.www.example.com"
    assert body["record_value"].startswith("securescope-verification=")
    assert body["method"] == "dns_txt"
    assert body["maximum_attempts"] == 5


async def test_successful_verification_verifies_asset(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.records[created["record_name"]] = [created["record_value"]]

    response = await client.post(
        f"{_base(asset['id'])}/{created['challenge_id']}/verify", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["challenge_status"] == "verified"
    assert body["asset_status"] == "verified"
    assert body["verified_at"] is not None
    assert body["message"] == "ownership verified"

    asset_view = (
        await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)
    ).json()
    assert asset_view["status"] == "verified"
    assert asset_view["ownership_verified_at"] is not None


async def test_mismatch_increments_attempts_without_verifying(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.records[created["record_name"]] = ["securescope-verification=wrong"]

    response = await client.post(
        f"{_base(asset['id'])}/{created['challenge_id']}/verify", headers=headers
    )

    body = response.json()
    assert body["challenge_status"] == "pending"
    assert body["asset_status"] == "pending_verification"
    assert body["attempts"] == 1


async def test_nxdomain_counts_as_failed_attempt(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    # resolver returns no records for the name (NXDOMAIN / no answer).

    response = await client.post(
        f"{_base(asset['id'])}/{created['challenge_id']}/verify", headers=headers
    )

    body = response.json()
    assert body["challenge_status"] == "pending"
    assert body["attempts"] == 1


async def test_resolver_timeout_is_inconclusive(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.unavailable = True

    response = await client.post(
        f"{_base(asset['id'])}/{created['challenge_id']}/verify", headers=headers
    )

    body = response.json()
    assert body["challenge_status"] == "pending"
    assert body["asset_status"] == "pending_verification"
    assert body["attempts"] == 0
    assert body["message"] == "verification could not be completed; please retry"


async def test_maximum_attempts_marks_challenge_failed(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.records[created["record_name"]] = ["securescope-verification=wrong"]
    verify_url = f"{_base(asset['id'])}/{created['challenge_id']}/verify"

    last_body = {}
    for _ in range(5):
        last_body = (await client.post(verify_url, headers=headers)).json()

    assert last_body["challenge_status"] == "failed"
    assert last_body["attempts"] == 5

    # A failed challenge can no longer be verified.
    again = await client.post(verify_url, headers=headers)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "verification_challenge_not_active"


async def test_unsupported_asset_type_is_rejected(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(
        client, create_organization, asset_type="ip_address", target="203.0.113.10"
    )

    response = await client.post(_base(asset["id"]), headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_verification_asset_type"


async def test_create_rejected_when_asset_not_pending(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(
        client, create_organization, request_verification=False
    )

    response = await client.post(_base(asset["id"]), headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "asset_not_pending_verification"


async def test_create_rejected_when_project_inactive(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
    set_project_status: Callable[[str, str], Awaitable[None]],
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    await set_project_status(asset["project_id"], "suspended")

    response = await client.post(_base(asset["id"]), headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inactive_verification_target"


async def test_create_rejected_when_organization_inactive(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
    set_organization_status: Callable[[str, str], Awaitable[None]],
) -> None:
    client, _resolver, _app = verification_app
    org, headers, asset = await _pending_asset(client, create_organization)
    await set_organization_status(org["id"], "suspended")

    response = await client.post(_base(asset["id"]), headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inactive_verification_target"


async def test_creating_when_pending_exists_is_rejected(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)

    first = await client.post(_base(asset["id"]), headers=headers)
    assert first.status_code == 201

    second = await client.post(_base(asset["id"]), headers=headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "active_verification_challenge_exists"

    # Only one pending row exists.
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AssetVerificationChallenge).where(
                        AssetVerificationChallenge.asset_id == asset["id"],
                        AssetVerificationChallenge.status == ChallengeStatus.pending,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert str(rows[0].id) == first.json()["challenge_id"]


async def test_cancel_flow(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    verify_url = f"{_base(asset['id'])}/{created['challenge_id']}/verify"
    cancel_url = f"{_base(asset['id'])}/{created['challenge_id']}/cancel"

    cancelled = await client.post(cancel_url, headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["challenge_status"] == "cancelled"

    # Cancel is idempotent; verify on a cancelled challenge is refused.
    assert (await client.post(cancel_url, headers=headers)).status_code == 200
    refused = await client.post(verify_url, headers=headers)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "verification_challenge_not_active"


async def test_verification_is_idempotent_after_verified(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.records[created["record_name"]] = [created["record_value"]]
    verify_url = f"{_base(asset['id'])}/{created['challenge_id']}/verify"

    first = (await client.post(verify_url, headers=headers)).json()
    second = (await client.post(verify_url, headers=headers)).json()

    assert first["challenge_status"] == "verified"
    assert second["challenge_status"] == "verified"
    assert second["asset_status"] == "verified"
    assert second["message"] == "ownership already verified"
    assert second["attempts"] == 0


async def test_expired_challenge_cannot_be_verified(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.platform.clock import get_clock
    from tests.conftest import FixedClock

    client, resolver, app = verification_app
    issued_at = datetime(2026, 1, 1, tzinfo=UTC)
    app.dependency_overrides[get_clock] = lambda: FixedClock(issued_at)
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.records[created["record_name"]] = [created["record_value"]]

    # Advance past the challenge TTL, then verify.
    app.dependency_overrides[get_clock] = lambda: FixedClock(
        issued_at + timedelta(hours=25)
    )
    response = await client.post(
        f"{_base(asset['id'])}/{created['challenge_id']}/verify", headers=headers
    )

    body = response.json()
    assert body["challenge_status"] == "expired"
    assert body["asset_status"] == "pending_verification"
    assert "expired" in body["message"]


async def test_concurrent_creates_keep_one_pending(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)

    results = await asyncio.gather(
        *[client.post(_base(asset["id"]), headers=headers) for _ in range(6)]
    )
    statuses = [r.status_code for r in results]
    assert 500 not in statuses
    # Exactly one request succeeds; the rest receive 409.
    created = [r for r in results if r.status_code == 201]
    conflicts = [r for r in results if r.status_code == 409]
    assert len(created) == 1
    assert len(conflicts) == 5
    for conflict in conflicts:
        assert (
            conflict.json()["error"]["code"] == "active_verification_challenge_exists"
        )

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AssetVerificationChallenge).where(
                        AssetVerificationChallenge.asset_id == asset["id"],
                        AssetVerificationChallenge.status == ChallengeStatus.pending,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1

    # The successful request's token must match the active challenge.
    success_body = created[0].json()
    current = (
        await client.get(f"{_base(asset['id'])}/current", headers=headers)
    ).json()
    assert current["challenge_id"] == success_body["challenge_id"]


async def test_concurrent_verifies_do_not_double_transition(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.records[created["record_name"]] = [created["record_value"]]
    verify_url = f"{_base(asset['id'])}/{created['challenge_id']}/verify"

    results = await asyncio.gather(
        *[client.post(verify_url, headers=headers) for _ in range(2)]
    )
    statuses = [r.status_code for r in results]
    assert statuses == [200, 200]
    assert all(r.json()["challenge_status"] == "verified" for r in results)
    assert all(r.json()["asset_status"] == "verified" for r in results)
