"""Security tests: token handling, tenant isolation, and the clock boundary."""

import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.modules.asset_verifications.models import AssetVerificationChallenge
from app.platform.clock import get_clock
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import FakeDnsResolver, FixedClock, tenant_headers
from tests.integration.test_asset_verification_api import _base, _pending_asset

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]


def _token_of(record_value: str) -> str:
    return record_value.split("=", 1)[1]


async def test_raw_token_is_never_persisted(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    token = _token_of(created["record_value"])

    async with session_factory() as session:
        row = (
            await session.execute(
                select(AssetVerificationChallenge).where(
                    AssetVerificationChallenge.id == UUID(created["challenge_id"])
                )
            )
        ).scalar_one()

    assert (
        row.token_digest
        == hashlib.sha256(created["record_value"].encode("utf-8")).hexdigest()
    )
    assert token not in row.token_digest
    assert token not in row.record_name
    assert row.token_last_four == token[-4:]


async def test_token_appears_only_in_create_response(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    token = _token_of(created["record_value"])

    current = await client.get(f"{_base(asset['id'])}/current", headers=headers)
    assert token not in current.text
    assert created["record_value"] not in current.text
    assert current.json()["token_last_four"] == token[-4:]

    resolver.records[created["record_name"]] = ["securescope-verification=wrong"]
    verify = await client.post(
        f"{_base(asset['id'])}/{created['challenge_id']}/verify", headers=headers
    )
    assert token not in verify.text


async def test_logs_and_responses_do_not_leak_raw_token(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
    caplog: Any,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)

    with caplog.at_level(logging.DEBUG):
        created = (await client.post(_base(asset["id"]), headers=headers)).json()
        token = _token_of(created["record_value"])
        resolver.records[created["record_name"]] = ["securescope-verification=wrong"]
        response = await client.post(
            f"{_base(asset['id'])}/{created['challenge_id']}/verify", headers=headers
        )

    assert token not in response.text
    assert token not in caplog.text


async def test_ownership_verified_at_uses_injected_clock(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, app = verification_app
    moment = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    app.dependency_overrides[get_clock] = lambda: FixedClock(moment)
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.records[created["record_name"]] = [created["record_value"]]

    verify = (
        await client.post(
            f"{_base(asset['id'])}/{created['challenge_id']}/verify", headers=headers
        )
    ).json()
    assert datetime.fromisoformat(verify["verified_at"]) == moment

    asset_view = (
        await client.get(f"/api/v1/assets/{asset['id']}", headers=headers)
    ).json()
    assert datetime.fromisoformat(asset_view["ownership_verified_at"]) == moment


async def test_cross_tenant_access_is_uniformly_not_found(
    verification_app: tuple[AsyncClient, FakeDnsResolver, Any],
    create_organization: CreateOrg,
) -> None:
    client, resolver, _app = verification_app
    _org, headers, asset = await _pending_asset(client, create_organization)
    created = (await client.post(_base(asset["id"]), headers=headers)).json()
    resolver.records[created["record_name"]] = [created["record_value"]]

    other = await create_organization(name="Other Org", slug="other-org")
    intruder = tenant_headers(other["id"])
    challenge_id = created["challenge_id"]
    base = _base(asset["id"])

    assert (await client.post(base, headers=intruder)).status_code == 404
    assert (await client.get(f"{base}/current", headers=intruder)).status_code == 404
    verify = await client.post(f"{base}/{challenge_id}/verify", headers=intruder)
    assert verify.status_code == 404
    cancel = await client.post(f"{base}/{challenge_id}/cancel", headers=intruder)
    assert cancel.status_code == 404

    # The legitimate tenant is unaffected.
    ok = await client.post(f"{base}/{challenge_id}/verify", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["challenge_status"] == "verified"
