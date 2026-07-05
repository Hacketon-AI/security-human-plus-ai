"""API/integration tests for validation executions."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import (
    WORKER_AUTH_TOKEN,
    CapturingValidationDispatcher,
    tenant_headers,
    worker_auth_headers,
)

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]

_TEMPLATE = "HTTP_SECURITY_HEADER_VALIDATION"
_DOC_SHA256 = "a" * 64


def _auth_payload(asset_id: str, *, risk_tier: str = "tier_1_safe") -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    return {
        "reference_number": "AUTH-VE-001",
        "title": "Assessment",
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=29)).isoformat(),
        "timezone": "UTC",
        "maximum_risk_tier": risk_tier,
        "production_testing_allowed": False,
        "core_banking_testing_allowed": False,
        "emergency_contact_name": "Officer",
        "emergency_contact_phone": "+1-555-0001",
        "authorization_document_name": "auth.pdf",
        "authorization_document_sha256": _DOC_SHA256,
        "scopes": [
            {
                "asset_id": asset_id,
                "maximum_requests_per_minute": 60,
                "maximum_concurrency": 5,
            }
        ],
    }


def _engagement_payload(
    auth_id: str, asset_id: str, *, risk_tier: str = "tier_1_safe"
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    return {
        "authorization_id": auth_id,
        "name": "Engagement",
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(days=7)).isoformat(),
        "timezone": "UTC",
        "max_risk_tier": risk_tier,
        "default_rate_limit_per_minute": 30,
        "default_concurrency_limit": 3,
        "emergency_contact_name": "Eng Officer",
        "emergency_contact_email": "eng@example.com",
        "scopes": [
            {
                "asset_id": asset_id,
                "allowed_ports": [443],
                "allowed_paths": ["/"],
                "rate_limit_per_minute": 20,
                "concurrency_limit": 2,
            }
        ],
    }


async def _make_verified_asset(
    client: AsyncClient,
    headers: dict[str, str],
    project_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "API",
    target: str = "https://api.example.com",
    environment: str = "staging",
) -> str:
    asset = (
        await client.post(
            "/api/v1/assets",
            json={
                "project_id": project_id,
                "name": name,
                "asset_type": "api",
                "environment": environment,
                "target": target,
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
    return str(asset["id"])


async def _setup(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    auth_risk_tier: str = "tier_1_safe",
    engagement_risk_tier: str = "tier_1_safe",
    activate_engagement: bool = True,
) -> dict[str, str]:
    """Create org/project/verified asset/active authorization/active engagement.

    Returns a dict of useful ids and the tenant headers.
    """
    org = await create_organization()
    headers = tenant_headers(org["id"])
    project = (
        await client.post("/api/v1/projects", json={"name": "P"}, headers=headers)
    ).json()
    asset_id = await _make_verified_asset(
        client, headers, project["id"], session_factory
    )

    auth = (
        await client.post(
            f"/api/v1/projects/{project['id']}/authorizations",
            json=_auth_payload(asset_id, risk_tier=auth_risk_tier),
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/authorizations/{auth['id']}/submit", headers=headers)
    await client.post(f"/api/v1/authorizations/{auth['id']}/activate", headers=headers)

    engagement = (
        await client.post(
            f"/api/v1/projects/{project['id']}/engagements",
            json=_engagement_payload(
                auth["id"], asset_id, risk_tier=engagement_risk_tier
            ),
            headers=headers,
        )
    ).json()
    engagement_scope_id = engagement["scopes"][0]["id"]
    if activate_engagement:
        await client.post(
            f"/api/v1/engagements/{engagement['id']}/schedule", headers=headers
        )
        await client.post(
            f"/api/v1/engagements/{engagement['id']}/activate", headers=headers
        )

    return {
        "org_id": str(org["id"]),
        "project_id": str(project["id"]),
        "asset_id": asset_id,
        "authorization_id": str(auth["id"]),
        "engagement_id": str(engagement["id"]),
        "engagement_scope_id": str(engagement_scope_id),
    }


async def _credential_revocation_state(
    session_factory: async_sessionmaker[AsyncSession], execution_id: str
) -> list[bool]:
    """Return ``revoked_at is not None`` for each credential of an execution.

    One boolean per persisted ``validation_worker_credentials`` row, so a test
    can assert both that a credential was issued and whether it is now revoked.
    """
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT revoked_at FROM validation_worker_credentials "
                    "WHERE execution_id = :execution_id"
                ),
                {"execution_id": execution_id},
            )
        ).all()
    return [row[0] is not None for row in rows]


def _create_body(ctx: dict[str, str], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "project_id": ctx["project_id"],
        "asset_id": ctx["asset_id"],
        "authorization_id": ctx["authorization_id"],
        "engagement_id": ctx["engagement_id"],
        "engagement_scope_id": ctx["engagement_scope_id"],
        "template_id": _TEMPLATE,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Happy path + dispatcher
# ---------------------------------------------------------------------------


async def test_create_queues_execution_happy_path(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "queued"
    assert body["outcome"] == "not_run"
    assert body["risk_tier"] == "tier_0_passive"
    assert body["queued_at"] is not None
    # The dispatcher captured exactly one immutable specification.
    assert len(dispatcher.dispatched) == 1


async def test_dispatcher_receives_immutable_specification(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    body = resp.json()
    payload = dispatcher.dispatched[0]
    spec = payload.execution_specification

    # The spec carries every scan-authorization control.
    assert spec["execution_id"] == body["id"]
    assert spec["template_id"] == _TEMPLATE
    assert spec["intrusive"] is False
    assert spec["asset_id"] == ctx["asset_id"]
    assert spec["authorization_id"] == ctx["authorization_id"]
    assert spec["engagement_id"] == ctx["engagement_id"]
    assert spec["scope"]["asset_id"] == ctx["asset_id"]
    # The frozen scope carries structured integer ports, never free text.
    assert spec["scope"]["allowed_ports"] == [443]
    assert spec["testing_window"]["start"] is not None
    assert spec["testing_window"]["end"] is not None
    assert spec["rate_limit_per_minute"] == 20
    # The kill-switch token is the abort key the worker polls; it is a required
    # dispatch control carried in the spec.
    assert spec["kill_switch_token"]
    assert payload.safety_snapshot["kill_switch_active"] is False


async def test_dispatch_payload_is_frozen_worker_contract(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The dispatch seam receives a frozen WorkerDispatchPayload — not the ORM
    row, not a raw dict — carrying only the worker-input fields."""
    from dataclasses import FrozenInstanceError, fields
    from uuid import UUID

    from app.modules.validation_executions.dispatch_contracts import (
        WorkerDispatchPayload,
    )
    from app.modules.validation_executions.models import ValidationExecution

    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    body = resp.json()
    payload = dispatcher.dispatched[0]

    # A typed, frozen value object — never the ORM model or an arbitrary dict.
    assert isinstance(payload, WorkerDispatchPayload)
    assert not isinstance(payload, ValidationExecution)
    assert not isinstance(payload, dict)

    # Exactly the worker-input field set: id + template + the three snapshots.
    assert {f.name for f in fields(payload)} == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }
    assert payload.execution_id == body["id"]
    assert payload.template_id == _TEMPLATE
    # The payload mirrors the persisted, frozen snapshots verbatim.
    async with session_factory() as session:
        stored = await session.get(ValidationExecution, UUID(body["id"]))
        assert stored is not None
        assert payload.execution_specification == stored.execution_specification
        assert payload.scope_snapshot == stored.scope_snapshot
        assert payload.safety_snapshot == stored.safety_snapshot

    # No tenant identity, credentials, or evidence leak into the payload.
    assert not hasattr(payload, "organization_id")
    assert "organization_id" not in payload.execution_specification
    assert "step_results" not in payload.execution_specification

    # Frozen: fields cannot be reassigned after construction.
    with pytest.raises(FrozenInstanceError):
        payload.execution_id = "tampered"  # type: ignore[misc]


async def test_no_scanner_logic_runs_in_api(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The API only records intent and hands a spec to the seam; the execution
    stays queued and nothing transitions it to executing without a worker."""
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    body = resp.json()

    # No step results produced inline; status remains queued (not executing).
    assert body["status"] == "queued"
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert body["step_results"] == []
    # The dispatcher only captured the spec; it ran nothing.
    assert dispatcher.dispatched == [dispatcher.dispatched[0]]


async def test_production_dispatcher_fails_closed(
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    app_client: Callable[..., Any],
) -> None:
    """With no dispatcher override (production wiring), dispatch is refused."""
    from app.config import Environment

    # Build via validation_app-equivalent but without overriding the dispatcher:
    # use the default (fail-closed) dispatcher in a development app so the rest
    # of the stack (tenant auth, provisioning) is available.
    async with app_client(Environment.development) as client:
        ctx = await _setup(client, create_organization, session_factory)
        resp = await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=tenant_headers(ctx["org_id"]),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "validation_dispatch_not_configured"

    # Fail-closed dispatch rolls the request transaction back: no execution row
    # is left queued without a worker pipeline to run it.
    async with session_factory() as session:
        count = (
            await session.execute(text("SELECT COUNT(*) FROM validation_executions"))
        ).scalar_one()
        assert count == 0


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


async def test_missing_tenant_context_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post("/api/v1/validation-executions", json=_create_body(ctx))
    assert resp.status_code == 401


async def test_cross_tenant_get_list_cancel_returns_404(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=tenant_headers(ctx["org_id"]),
        )
    ).json()

    other = await create_organization(name="Other", slug="other-ve")
    attacker = tenant_headers(other["id"])

    assert (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}", headers=attacker
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/validation-executions/{execution['id']}/cancel",
            headers=attacker,
        )
    ).status_code == 404
    # List under the attacker's tenant for the victim project is empty.
    listed = await client.get(
        f"/api/v1/projects/{ctx['project_id']}/validation-executions",
        headers=attacker,
    )
    assert listed.status_code == 200
    assert listed.json() == []


async def test_organization_id_not_accepted_from_body(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx, organization_id=ctx["org_id"]),
        headers=tenant_headers(ctx["org_id"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Asset eligibility
# ---------------------------------------------------------------------------


async def test_reject_unverified_asset(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    # Suspend the asset after setup.
    async with session_factory() as session:
        await session.execute(
            text("UPDATE assets SET status = :s WHERE id = :id"),
            {"s": "suspended", "id": ctx["asset_id"]},
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_execution_scope"


async def test_reject_asset_outside_engagement_scope(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    # A second verified asset not in the engagement scope.
    headers = tenant_headers(ctx["org_id"])
    other_asset = await _make_verified_asset(
        client,
        headers,
        ctx["project_id"],
        session_factory,
        name="Other",
        target="https://other.example.com",
    )

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx, asset_id=other_asset),
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_execution_scope"


async def test_invalid_authorization_ports_block_before_dispatch(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A malformed stored port value blocks queueing before the worker seam.

    Schema validation keeps free text out on write, so a malformed value can
    only arise from legacy/corrupted data. Inject it directly: clear the
    engagement port override so resolution falls back to the authorization
    scope, then corrupt that scope's ``allowed_ports`` to a JSON string. The
    snapshot builder must reject it with a domain error before anything is
    queued or dispatched.
    """
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE engagement_scopes SET allowed_ports = NULL "
                "WHERE engagement_id = :eid"
            ),
            {"eid": ctx["engagement_id"]},
        )
        await session.execute(
            text(
                "UPDATE authorization_scopes SET allowed_ports = CAST(:v AS json) "
                "WHERE authorization_id = :aid"
            ),
            {"v": '"443,8443"', "aid": ctx["authorization_id"]},
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_execution_scope"
    # The malformed value never reached the worker seam.
    assert dispatcher.dispatched == []


# ---------------------------------------------------------------------------
# Authorization eligibility
# ---------------------------------------------------------------------------


async def test_reject_revoked_authorization(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    await client.post(
        f"/api/v1/authorizations/{ctx['authorization_id']}/revoke",
        json={"reason": "test"},
        headers=headers,
    )

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "execution_eligibility_blocked"


async def test_reject_expired_authorization(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    async with session_factory() as session:
        await session.execute(
            text("UPDATE authorizations SET status = :s WHERE id = :id"),
            {"s": "expired", "id": ctx["authorization_id"]},
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "execution_eligibility_blocked"


# ---------------------------------------------------------------------------
# Engagement eligibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["paused", "completed", "cancelled", "scheduled"])
async def test_reject_non_active_engagement(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    status: str,
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    async with session_factory() as session:
        await session.execute(
            text("UPDATE engagements SET status = :s WHERE id = :id"),
            {"s": status, "id": ctx["engagement_id"]},
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "execution_eligibility_blocked"


async def test_reject_engagement_outside_time_window(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    # Move the engagement window entirely into the past.
    now = datetime.now(tz=UTC)
    async with session_factory() as session:
        await session.execute(
            text("UPDATE engagements SET starts_at = :s, ends_at = :e WHERE id = :id"),
            {
                "s": now - timedelta(days=3),
                "e": now - timedelta(days=1),
                "id": ctx["engagement_id"],
            },
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "execution_eligibility_blocked"


async def test_reject_kill_switch_active_engagement(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    await client.post(
        f"/api/v1/engagements/{ctx['engagement_id']}/kill-switch",
        json={"active": True, "reason": "halt"},
        headers=tenant_headers(ctx["org_id"]),
    )

    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "execution_eligibility_blocked"


# ---------------------------------------------------------------------------
# Risk tier
# ---------------------------------------------------------------------------


async def test_template_within_risk_tiers_is_allowed(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # tier_0 template under tier_0 authorization + engagement.
    client, _dispatcher, _app = validation_app
    ctx = await _setup(
        client,
        create_organization,
        session_factory,
        auth_risk_tier="tier_0_passive",
        engagement_risk_tier="tier_0_passive",
    )
    resp = await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=tenant_headers(ctx["org_id"]),
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


async def test_idempotency_same_key_same_request_returns_same_execution(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    body = _create_body(ctx, idempotency_key="key-1")

    first = await client.post(
        "/api/v1/validation-executions", json=body, headers=headers
    )
    second = await client.post(
        "/api/v1/validation-executions", json=body, headers=headers
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    # The repeat returns the existing execution and does not dispatch again.
    assert len(dispatcher.dispatched) == 1


async def test_idempotency_same_key_different_request_conflicts(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    # Second verified asset added to BOTH the authorization and engagement so it
    # is independently eligible — only the idempotency key collides.
    await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx, idempotency_key="key-2"),
        headers=headers,
    )

    # Same key, different template material (different engagement_scope_id is
    # hard to forge; use a different asset by reusing the key with a changed
    # requested_by is not material — instead change template_id to a bogus one
    # which is rejected earlier, so change asset to a non-scoped asset to make
    # the request materially different while still hitting the key check first).
    different = _create_body(
        ctx, idempotency_key="key-2", asset_id=str(ctx["authorization_id"])
    )
    resp = await client.post(
        "/api/v1/validation-executions", json=different, headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_conflict"


# ---------------------------------------------------------------------------
# Cancel + state machine
# ---------------------------------------------------------------------------


async def test_cancel_queued_execution(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/cancel", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["cancelled_at"] is not None


async def test_cannot_cancel_terminal_execution(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/cancel", headers=headers
    )

    again = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/cancel", headers=headers
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "execution_immutable"


async def test_cancel_revokes_worker_credential(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Cancelling a queued execution revokes its per-execution credential.

    A terminal cancellation must close the worker credential so a still-running
    or redelivered worker cannot keep authenticating hooks for the stopped run.
    """
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()

    # A credential is minted at dispatch and is still live before cancellation.
    before = await _credential_revocation_state(session_factory, execution["id"])
    assert before == [False]

    resp = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/cancel", headers=headers
    )
    assert resp.status_code == 200

    after = await _credential_revocation_state(session_factory, execution["id"])
    assert after == [True]


# ---------------------------------------------------------------------------
# Worker hooks
# ---------------------------------------------------------------------------


async def test_worker_started_transition(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "executing"
    assert resp.json()["started_at"] is not None


async def test_worker_finished_succeeded(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )

    resp = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json={
            "succeeded": True,
            "outcome": "validated",
            "result_summary": "All headers present",
            "steps": [
                {
                    "step_name": "check-hsts",
                    "status": "passed",
                    "evidence": {"strict_transport_security": "max-age=63072000"},
                }
            ],
        },
        headers=worker_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["outcome"] == "validated"
    assert body["finished_at"] is not None
    # The worker response is minimized: no spec, snapshots, kill-switch token, or
    # step evidence is reflected back to the worker.
    for leaked in (
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
        "kill_switch_token",
        "step_results",
    ):
        assert leaked not in body

    # Step results and evidence are persisted and visible to the tenant via the
    # user-facing GET, which is unchanged.
    got = await client.get(
        f"/api/v1/validation-executions/{execution['id']}", headers=headers
    )
    user_body = got.json()
    assert len(user_body["step_results"]) == 1
    assert user_body["step_results"][0]["status"] == "passed"
    assert "execution_specification" in user_body


async def test_worker_finished_revokes_worker_credential(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A terminal worker-finished revokes the per-execution credential.

    Once a run reports a terminal verdict the credential must close, so a broker
    redelivery of the finish (or a lingering worker) cannot re-authenticate
    against the completed execution (design → Expiry and revocation).
    """
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )

    # Still live while the run is executing.
    assert await _credential_revocation_state(session_factory, execution["id"]) == [
        False
    ]

    resp = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json={"succeeded": True, "outcome": "validated"},
        headers=worker_auth_headers(),
    )
    assert resp.status_code == 200

    after = await _credential_revocation_state(session_factory, execution["id"])
    assert after == [True]


async def test_worker_finished_failed_safely(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )

    resp = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json={
            "succeeded": False,
            "outcome": "failed_safely",
            "error_code": "timeout",
            "error_message": "target did not respond",
        },
        headers=worker_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["outcome"] == "failed_safely"
    # The minimized worker response carries no error_code/spec/snapshot fields.
    for leaked in (
        "error_code",
        "error_message",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    ):
        assert leaked not in body

    # The sanitized error_code is persisted and readable via the user GET.
    got = await client.get(
        f"/api/v1/validation-executions/{execution['id']}", headers=headers
    )
    assert got.json()["error_code"] == "timeout"


async def test_terminal_states_immutable_for_worker(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )
    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json={"succeeded": True, "outcome": "validated"},
        headers=worker_auth_headers(),
    )

    # A second finish that carries a *different* verdict must never mutate a
    # terminal execution: it is rejected with a typed conflict. (An identical
    # redelivery is instead a safe idempotent no-op — pinned separately by
    # test_worker_finished_idempotent_no_duplicate_step_results.)
    resp = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json={"succeeded": False, "outcome": "failed_safely"},
        headers=worker_auth_headers(),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_execution_state_transition"

    # The originally recorded verdict is untouched by the rejected conflict.
    stored = (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}", headers=headers
        )
    ).json()
    assert stored["status"] == "succeeded"
    assert stored["outcome"] == "validated"


# ---------------------------------------------------------------------------
# Worker authentication
# ---------------------------------------------------------------------------


async def _queued_execution(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Set up and queue one execution; return ctx plus the execution id."""
    ctx = await _setup(client, create_organization, session_factory)
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=tenant_headers(ctx["org_id"]),
        )
    ).json()
    ctx["execution_id"] = str(execution["id"])
    return ctx


async def test_worker_started_succeeds_with_worker_token_and_no_tenant_header(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _queued_execution(client, create_organization, session_factory)

    resp = await client.post(
        f"/api/v1/validation-executions/{ctx['execution_id']}/worker-started",
        headers=worker_auth_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "executing"
    assert body["started_at"] is not None
    # Minimized response: the spec, snapshots, and kill-switch token never leave
    # the control plane through a worker hook.
    for leaked in (
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
        "kill_switch_token",
        "step_results",
    ):
        assert leaked not in body


async def test_worker_finished_succeeds_with_worker_token_and_no_tenant_header(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _queued_execution(client, create_organization, session_factory)
    await client.post(
        f"/api/v1/validation-executions/{ctx['execution_id']}/worker-started",
        headers=worker_auth_headers(),
    )

    resp = await client.post(
        f"/api/v1/validation-executions/{ctx['execution_id']}/worker-finished",
        json={"succeeded": True, "outcome": "validated"},
        headers=worker_auth_headers(),
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"


async def test_worker_started_rejects_missing_token(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _queued_execution(client, create_organization, session_factory)

    resp = await client.post(
        f"/api/v1/validation-executions/{ctx['execution_id']}/worker-started",
    )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "worker_authentication_failed"


async def test_worker_finished_rejects_invalid_token(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _queued_execution(client, create_organization, session_factory)

    resp = await client.post(
        f"/api/v1/validation-executions/{ctx['execution_id']}/worker-finished",
        json={"succeeded": True, "outcome": "validated"},
        headers=worker_auth_headers(WORKER_AUTH_TOKEN + "-wrong"),
    )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "worker_authentication_failed"


async def test_worker_hook_rejects_tenant_header_as_substitute(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # A tenant credential must not authenticate a machine hook: presenting only
    # X-Organization-Id (and no worker token) is rejected like any missing token.
    client, _dispatcher, _app = validation_app
    ctx = await _queued_execution(client, create_organization, session_factory)

    resp = await client.post(
        f"/api/v1/validation-executions/{ctx['execution_id']}/worker-started",
        headers=tenant_headers(ctx["org_id"]),
    )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "worker_authentication_failed"


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------


async def test_worker_evidence_is_sanitized(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )

    huge_value = "x" * 5000
    resp = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json={
            "succeeded": True,
            "outcome": "validated",
            "steps": [
                {
                    "step_name": "header-check",
                    "status": "passed",
                    "evidence": {"k": huge_value},
                }
            ],
        },
        headers=worker_auth_headers(),
    )
    # The minimized worker response carries no evidence at all.
    assert "step_results" not in resp.json()

    # Evidence is persisted (and bounded by the service) on the user-facing GET.
    got = await client.get(
        f"/api/v1/validation-executions/{execution['id']}", headers=headers
    )
    step = got.json()["step_results"][0]
    assert len(step["evidence"]["k"]) <= 2000


# ---------------------------------------------------------------------------
# List scoping
# ---------------------------------------------------------------------------


async def test_list_is_tenant_and_project_scoped(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx),
        headers=headers,
    )

    listed = await client.get(
        f"/api/v1/projects/{ctx['project_id']}/validation-executions",
        headers=headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # A different project under the same tenant has none.
    other_project = (
        await client.post("/api/v1/projects", json={"name": "P2"}, headers=headers)
    ).json()
    listed2 = await client.get(
        f"/api/v1/projects/{other_project['id']}/validation-executions",
        headers=headers,
    )
    assert listed2.status_code == 200
    assert listed2.json() == []


async def test_concurrent_create_with_idempotency_key_keeps_one(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    body = _create_body(ctx, idempotency_key="race-key")

    results = await asyncio.gather(
        *[
            client.post("/api/v1/validation-executions", json=body, headers=headers)
            for _ in range(4)
        ],
        return_exceptions=True,
    )
    statuses = [r.status_code for r in results if not isinstance(r, BaseException)]
    # No 500s; every settled response is a success or a benign idempotency race.
    assert all(s in (201, 409) for s in statuses)

    listed = (
        await client.get(
            f"/api/v1/projects/{ctx['project_id']}/validation-executions",
            headers=headers,
        )
    ).json()
    # Exactly one row persisted for the key.
    keyed = [e for e in listed if e["idempotency_key"] == "race-key"]
    assert len(keyed) == 1


# ---------------------------------------------------------------------------
# Worker-hook idempotency (broker redelivery safety)
# ---------------------------------------------------------------------------


_MINIMAL_RESPONSE_FORBIDDEN = (
    "execution_specification",
    "scope_snapshot",
    "safety_snapshot",
    "kill_switch_token",
    "step_results",
)


async def _start_executing(client: AsyncClient, ctx: dict[str, str]) -> dict[str, Any]:
    """Create an execution and post worker-started; return the execution row."""
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )
    return execution


def _finished_payload(
    *,
    succeeded: bool = True,
    outcome: str = "validated",
    result_summary: str = "All headers present",
    step_name: str = "check-hsts",
    step_status: str = "passed",
    step_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "succeeded": succeeded,
        "outcome": outcome,
        "result_summary": result_summary,
        "steps": [
            {
                "step_name": step_name,
                "status": step_status,
                "evidence": step_evidence
                or {"strict_transport_security": "max-age=63072000"},
            }
        ],
    }


def _assert_worker_response_minimal(body: dict[str, Any]) -> None:
    """The worker-hook response must not echo spec, snapshots, evidence, or the
    kill-switch token — even after a duplicate redelivery.

    The worker already holds what it needs; nothing sensitive should be
    reflected back over the wire (see ``WorkerExecutionStateResponse``
    docstring in ``schemas.py``).
    """
    for leaked in (
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
        "step_results",
        "kill_switch_token",
        "evidence",
    ):
        assert leaked not in body, f"duplicate worker hook leaked {leaked!r}"


async def test_worker_started_idempotent_does_not_reset_started_at(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = await _start_executing(client, ctx)

    # Repeat worker-started — broker redelivery scenario.
    first_get = await client.get(
        f"/api/v1/validation-executions/{execution['id']}",
        headers=tenant_headers(ctx["org_id"]),
    )
    first_started_at = first_get.json()["started_at"]

    repeat = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )
    assert repeat.status_code == 200
    body = repeat.json()
    assert body["status"] == "executing"
    # started_at is unchanged across the duplicate hook.
    assert body["started_at"] == first_started_at
    # Response stays minimal — no spec/snapshot/evidence/token leak.
    for leaked in _MINIMAL_RESPONSE_FORBIDDEN:
        assert leaked not in body


async def test_worker_started_after_terminal_state_is_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A late worker-started must never revive a terminal execution."""
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = await _start_executing(client, ctx)

    finish = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json=_finished_payload(),
        headers=worker_auth_headers(),
    )
    assert finish.status_code == 200

    late = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-started",
        headers=worker_auth_headers(),
    )
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "invalid_execution_state_transition"


async def test_worker_finished_idempotent_no_duplicate_step_results(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = await _start_executing(client, ctx)
    headers = tenant_headers(ctx["org_id"])
    payload = _finished_payload()

    first = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json=payload,
        headers=worker_auth_headers(),
    )
    assert first.status_code == 200
    first_body = first.json()

    second = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json=payload,
        headers=worker_auth_headers(),
    )
    assert second.status_code == 200
    second_body = second.json()

    # Same terminal status, outcome, and finished_at — no overwrite.
    assert second_body["status"] == first_body["status"]
    assert second_body["outcome"] == first_body["outcome"]
    assert second_body["finished_at"] == first_body["finished_at"]
    # The duplicate response carries nothing sensitive back.
    for leaked in _MINIMAL_RESPONSE_FORBIDDEN:
        assert leaked not in second_body

    # The user-facing GET shows exactly one step row, not two.
    user_body = (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}", headers=headers
        )
    ).json()
    assert len(user_body["step_results"]) == 1


async def test_worker_finished_step_order_insensitive(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Same steps in a different order are still the same semantic result."""
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = await _start_executing(client, ctx)

    first_payload = {
        "succeeded": True,
        "outcome": "validated",
        "result_summary": "All headers present",
        "steps": [
            {"step_name": "check-hsts", "status": "passed", "evidence": {"a": "1"}},
            {"step_name": "check-csp", "status": "passed", "evidence": {"b": "2"}},
        ],
    }
    first = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json=first_payload,
        headers=worker_auth_headers(),
    )
    assert first.status_code == 200

    second_payload = dict(first_payload)
    second_payload["steps"] = list(reversed(first_payload["steps"]))
    second = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json=second_payload,
        headers=worker_auth_headers(),
    )
    assert second.status_code == 200

    user_body = (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}",
            headers=tenant_headers(ctx["org_id"]),
        )
    ).json()
    # Still exactly two steps — no doubling from the reordered redelivery.
    assert len(user_body["step_results"]) == 2


async def test_worker_finished_different_result_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = await _start_executing(client, ctx)

    await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json=_finished_payload(succeeded=True, outcome="validated"),
        headers=worker_auth_headers(),
    )

    conflict = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json=_finished_payload(
            succeeded=False, outcome="failed_safely", result_summary="different"
        ),
        headers=worker_auth_headers(),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "invalid_execution_state_transition"

    # Stored result is unchanged.
    user_body = (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}",
            headers=tenant_headers(ctx["org_id"]),
        )
    ).json()
    assert user_body["status"] == "succeeded"
    assert user_body["outcome"] == "validated"


async def test_worker_finished_after_cancelled_is_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A redelivered worker-finished must not revive a cancelled execution."""
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = await _start_executing(client, ctx)
    headers = tenant_headers(ctx["org_id"])

    cancel = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/cancel",
        headers=headers,
    )
    assert cancel.status_code == 200

    late = await client.post(
        f"/api/v1/validation-executions/{execution['id']}/worker-finished",
        json=_finished_payload(),
        headers=worker_auth_headers(),
    )
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "invalid_execution_state_transition"

    user_body = (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}", headers=headers
        )
    ).json()
    # Status remains cancelled and no result was recorded.
    assert user_body["status"] == "cancelled"
    assert user_body["result_summary"] is None


async def test_concurrent_worker_started_sets_started_at_once(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    headers = tenant_headers(ctx["org_id"])
    execution = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=headers,
        )
    ).json()

    results = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/validation-executions/{execution['id']}/worker-started",
                headers=worker_auth_headers(),
            )
            for _ in range(4)
        ],
        return_exceptions=True,
    )
    statuses = [r.status_code for r in results if not isinstance(r, BaseException)]
    # Every settled response is a benign success (idempotent) or a serialized
    # transient that the worker will see as already-executing on retry.
    assert all(s in (200, 409) for s in statuses)
    successes = [
        r for r in results if not isinstance(r, BaseException) and r.status_code == 200
    ]
    assert successes, "at least one worker-started must succeed"

    # Every 200 is a minimal worker-state response — duplicate idempotent
    # returns must not leak the spec, snapshots, or kill-switch token.
    for response in successes:
        _assert_worker_response_minimal(response.json())

    user_body = (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}", headers=headers
        )
    ).json()
    assert user_body["status"] == "executing"
    # All successful responses report the same started_at — set once.
    started_ats = {r.json()["started_at"] for r in successes}
    assert len(started_ats) == 1


async def test_concurrent_duplicate_worker_finished_inserts_steps_once(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = await _start_executing(client, ctx)
    headers = tenant_headers(ctx["org_id"])
    payload = _finished_payload()

    results = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/validation-executions/{execution['id']}/worker-finished",
                json=payload,
                headers=worker_auth_headers(),
            )
            for _ in range(4)
        ],
        return_exceptions=True,
    )
    statuses = [r.status_code for r in results if not isinstance(r, BaseException)]
    # No 500s; every settled response is either an idempotent success or a
    # benign serialization conflict from the row lock.
    assert all(s in (200, 409) for s in statuses)
    # Every 200 is a minimal worker-state response — no spec, snapshot,
    # evidence, or kill-switch token reflected by the duplicate path.
    for response in results:
        if not isinstance(response, BaseException) and response.status_code == 200:
            _assert_worker_response_minimal(response.json())

    user_body = (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}", headers=headers
        )
    ).json()
    # Exactly one step row, regardless of how many redelivery attempts landed.
    assert len(user_body["step_results"]) == 1
    assert user_body["status"] == "succeeded"
    # finished_at is set once: the duplicates must not overwrite it.
    assert user_body["finished_at"] is not None


async def test_concurrent_duplicate_worker_finished_conflict_preserves_first(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Concurrent conflicting worker-finished calls converge atomically.

    Two redelivery attempts arrive with materially different verdicts. The
    row lock (``SELECT … FOR UPDATE`` in
    ``ValidationExecutionService.worker_finished``) serializes them so the
    first writer wins and the second is rejected with a typed 409 — the
    stored verdict is one of the submitted payloads, never a partial mix,
    and the step set is consistent with that verdict only. This pins the
    "two writers, one row" guarantee that broker redelivery would otherwise
    leave open.
    """
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution = await _start_executing(client, ctx)
    headers = tenant_headers(ctx["org_id"])

    succeeded_payload = _finished_payload(
        succeeded=True,
        outcome="validated",
        result_summary="All headers present",
        step_name="check-hsts",
        step_status="passed",
    )
    failed_payload = _finished_payload(
        succeeded=False,
        outcome="failed_safely",
        result_summary="header check failed safely",
        step_name="check-hsts",
        step_status="failed",
        step_evidence={"detail": "transport error"},
    )

    results = await asyncio.gather(
        client.post(
            f"/api/v1/validation-executions/{execution['id']}/worker-finished",
            json=succeeded_payload,
            headers=worker_auth_headers(),
        ),
        client.post(
            f"/api/v1/validation-executions/{execution['id']}/worker-finished",
            json=failed_payload,
            headers=worker_auth_headers(),
        ),
        return_exceptions=True,
    )

    statuses = [r.status_code for r in results if not isinstance(r, BaseException)]
    # Each settled response is either the first-writer success or the typed
    # serialization/state-transition rejection — never a 500 or an
    # IntegrityError surfaced to the caller.
    assert all(s in (200, 409) for s in statuses), statuses
    successes = [
        r for r in results if not isinstance(r, BaseException) and r.status_code == 200
    ]
    conflicts = [
        r for r in results if not isinstance(r, BaseException) and r.status_code == 409
    ]
    assert len(successes) == 1, "exactly one writer wins under the row lock"
    assert len(conflicts) == 1, "the conflicting writer must be rejected, not retried"
    assert conflicts[0].json()["error"]["code"] == "invalid_execution_state_transition"

    # The success response is minimal — duplicates never widen the contract.
    _assert_worker_response_minimal(successes[0].json())

    user_body = (
        await client.get(
            f"/api/v1/validation-executions/{execution['id']}", headers=headers
        )
    ).json()
    # The stored result is exactly one of the two submitted verdicts — not a
    # partial blend of summary/outcome/steps from both.
    assert user_body["status"] in ("succeeded", "failed")
    if user_body["status"] == "succeeded":
        assert user_body["outcome"] == "validated"
        assert user_body["result_summary"] == "All headers present"
        assert len(user_body["step_results"]) == 1
        assert user_body["step_results"][0]["status"] == "passed"
    else:
        assert user_body["outcome"] == "failed_safely"
        assert user_body["result_summary"] == "header check failed safely"
        assert len(user_body["step_results"]) == 1
        assert user_body["step_results"][0]["status"] == "failed"
