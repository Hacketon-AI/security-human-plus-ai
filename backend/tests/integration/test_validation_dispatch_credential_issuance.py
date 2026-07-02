"""Step 4A — dispatch-side per-execution worker credential issuance + handoff.

These integration tests pin the behaviour added in Step 4A against a real
PostgreSQL: ``create_and_queue`` mints exactly one per-execution worker
credential (granting both worker hooks, bounded by the TTL/cap and the
engagement window), the raw token reaches the dispatcher only via the
:class:`WorkerCredentialHandoff` side-channel and never the broker
payload/envelope/queue/logs/audit/API response, issuance failure fails closed
(no dispatch), and a dispatch failure rolls the credential back with the
execution. The minted credential authenticates the worker hooks even with the
shared-token fallback disabled.

Full worker bootstrap (consuming the handoff to launch a real isolated worker)
is deliberately out of scope — see docs/validation-worker-credentials-design.md.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from app.config import Environment, Settings
from app.main import create_app
from app.modules.validation_executions.broker_contracts import build_dispatch_envelope
from app.modules.validation_executions.celery_publisher import envelope_to_dict
from app.modules.validation_executions.credential_issuer import (
    PersistedWorkerCredentialIssuer,
)
from app.modules.validation_executions.dispatcher import get_validation_dispatcher
from app.modules.validation_executions.models import ValidationWorkerCredential
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialIssueOutcome,
    WorkerCredentialIssueResult,
    compute_worker_token_digest,
)
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import (
    WORKER_AUTH_TOKEN,
    CapturingValidationDispatcher,
    tenant_headers,
)
from tests.integration.test_validation_executions_api import _create_body, _setup

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _credentials_for(
    session_factory: async_sessionmaker[AsyncSession], execution_id: str
) -> list[ValidationWorkerCredential]:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ValidationWorkerCredential).where(
                        ValidationWorkerCredential.execution_id == UUID(execution_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


async def _count_rows(
    session_factory: async_sessionmaker[AsyncSession], table: str
) -> int:
    async with session_factory() as session:
        return (
            await session.execute(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
        ).scalar_one()


async def _create_execution(
    client: AsyncClient,
    ctx: dict[str, str],
    **overrides: Any,
) -> Any:
    return await client.post(
        "/api/v1/validation-executions",
        json=_create_body(ctx, **overrides),
        headers=tenant_headers(ctx["org_id"]),
    )


@asynccontextmanager
async def _capturing_app(
    migrated_dsn: str, *, fallback_enabled: bool
) -> AsyncIterator[tuple[AsyncClient, CapturingValidationDispatcher]]:
    """Build an app with a capturing dispatcher and a chosen fallback flag.

    Mirrors the ``validation_app`` fixture but lets a test pick whether the
    shared-token fallback is enabled, so the minted per-execution credential
    can be exercised against a fallback-off app.
    """
    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(migrated_dsn),
        worker_auth_token=SecretStr(WORKER_AUTH_TOKEN),
        worker_shared_token_fallback_enabled=fallback_enabled,
    )
    app = create_app(settings)
    dispatcher = CapturingValidationDispatcher()
    app.dependency_overrides[get_validation_dispatcher] = lambda: dispatcher
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, dispatcher


# ---------------------------------------------------------------------------
# Issuance shape
# ---------------------------------------------------------------------------


async def test_create_and_queue_issues_exactly_one_credential(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await _create_execution(client, ctx)
    assert resp.status_code == 201
    execution_id = resp.json()["id"]

    creds = await _credentials_for(session_factory, execution_id)
    assert len(creds) == 1
    # Exactly one handoff was passed to the dispatch boundary for this create.
    assert len(dispatcher.handoffs) == 1
    assert dispatcher.handoffs[0] is not None
    assert dispatcher.handoffs[0].execution_id == execution_id


async def test_credential_allowed_actions_are_both_worker_hooks(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution_id = (await _create_execution(client, ctx)).json()["id"]

    creds = await _credentials_for(session_factory, execution_id)
    assert sorted(creds[0].allowed_actions) == ["worker_finished", "worker_started"]


async def test_credential_expiry_respects_default_ttl(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution_id = (await _create_execution(client, ctx)).json()["id"]

    cred = (await _credentials_for(session_factory, execution_id))[0]
    # Positive, and never beyond the 1h default TTL (well under the 24h cap).
    assert cred.expires_at > cred.issued_at
    assert cred.expires_at - cred.issued_at <= timedelta(hours=1) + timedelta(seconds=5)
    # The handoff mirrors the persisted expiry.
    assert dispatcher.handoffs[0] is not None
    assert dispatcher.handoffs[0].expires_at == cred.expires_at


async def test_credential_expiry_capped_to_engagement_window(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """When the engagement ends sooner than the default TTL, expiry is capped."""
    client, _dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    # Shrink the engagement window to 20 minutes (still in the future, so the
    # execution stays eligible), well under the 1h default credential TTL.
    window_end = datetime.now(tz=UTC) + timedelta(minutes=20)
    async with session_factory() as session:
        await session.execute(
            text("UPDATE engagements SET ends_at = :e WHERE id = :id"),
            {"e": window_end, "id": ctx["engagement_id"]},
        )
        await session.commit()

    execution_id = (await _create_execution(client, ctx)).json()["id"]
    cred = (await _credentials_for(session_factory, execution_id))[0]

    # Capped to the (shorter) engagement window, not the full 1h default.
    assert cred.expires_at - cred.issued_at < timedelta(hours=1)
    assert cred.expires_at <= window_end + timedelta(seconds=5)


# ---------------------------------------------------------------------------
# Raw-token containment
# ---------------------------------------------------------------------------


async def test_raw_token_is_not_stored_in_db(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution_id = (await _create_execution(client, ctx)).json()["id"]

    handoff = dispatcher.handoffs[0]
    assert handoff is not None
    raw = handoff.raw_token.get_secret_value()

    cred = (await _credentials_for(session_factory, execution_id))[0]
    # Only the digest is stored; the raw token is never persisted.
    assert cred.token_digest == compute_worker_token_digest(raw)
    assert cred.token_digest != raw
    assert raw not in str(cred.__dict__)


async def test_raw_token_not_in_dispatch_payload(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    await _create_execution(client, ctx)

    handoff = dispatcher.handoffs[0]
    assert handoff is not None
    raw = handoff.raw_token.get_secret_value()

    payload = dispatcher.dispatched[0]
    assert raw not in str(payload.execution_specification)
    assert raw not in str(payload.scope_snapshot)
    assert raw not in str(payload.safety_snapshot)
    assert raw not in str(payload)


async def test_raw_token_not_in_dispatch_envelope(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    await _create_execution(client, ctx)

    handoff = dispatcher.handoffs[0]
    assert handoff is not None
    raw = handoff.raw_token.get_secret_value()

    # The envelope the broker would carry is built from the captured payload;
    # it must contain neither the raw token nor the credential_id.
    envelope = build_dispatch_envelope(
        dispatcher.dispatched[0],
        message_id="msg-1",
        created_at=datetime.now(tz=UTC).isoformat(),
        attempt=1,
    )
    envelope_dict = envelope_to_dict(envelope)
    assert raw not in str(envelope_dict)
    assert handoff.credential_id not in str(envelope_dict)


async def test_raw_token_not_logged_during_create(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The raw token reaches neither the issuer log nor the audit event.

    Log capture via ``caplog`` is fragile here because ``instrument_app``
    reconfigures the logging hierarchy (the Step 3 auth test hit the same
    issue). Instead we record the two module loggers on the create path
    directly, which is deterministic: assert the raw token appears in none
    of the emitted lines, while the opaque ``credential_id`` does (it is safe
    to audit).
    """
    from app.modules.validation_executions import audit as audit_module
    from app.modules.validation_executions import credential_issuer as issuer_module

    records: list[str] = []

    class _Recorder:
        def _capture(self, fmt: Any, *args: Any, **kwargs: Any) -> None:
            parts = [str(fmt), *(str(a) for a in args)]
            if kwargs:
                parts.append(str(kwargs))
            records.append(" ".join(parts))

        def info(self, fmt: Any, *args: Any, **kwargs: Any) -> None:
            self._capture(fmt, *args, **kwargs)

        def warning(self, fmt: Any, *args: Any, **kwargs: Any) -> None:
            self._capture(fmt, *args, **kwargs)

        def debug(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
            pass

    monkeypatch.setattr(issuer_module, "_logger", _Recorder())
    monkeypatch.setattr(audit_module, "_logger", _Recorder())

    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    await _create_execution(client, ctx)

    handoff = dispatcher.handoffs[0]
    assert handoff is not None
    raw = handoff.raw_token.get_secret_value()

    log_text = "\n".join(records)
    # Sanity: the issuer + audit actually emitted lines on the create path.
    assert log_text
    # The raw token appears in none of them...
    assert raw not in log_text
    # ...while the opaque credential_id is recorded (safe for the audit trail).
    assert handoff.credential_id in log_text


async def test_api_response_excludes_credential_fields(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    resp = await _create_execution(client, ctx)
    body = resp.json()

    for forbidden in ("credential_id", "raw_token", "token_digest"):
        assert forbidden not in body
    handoff = dispatcher.handoffs[0]
    assert handoff is not None
    # Neither the raw token nor the credential_id leaks into the response body.
    assert handoff.raw_token.get_secret_value() not in resp.text
    assert handoff.credential_id not in resp.text


# ---------------------------------------------------------------------------
# Worker hook authentication with the minted credential
# ---------------------------------------------------------------------------


async def test_worker_hook_authenticates_with_minted_credential(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)
    execution_id = (await _create_execution(client, ctx)).json()["id"]

    handoff = dispatcher.handoffs[0]
    assert handoff is not None
    token = handoff.raw_token.get_secret_value()

    started = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started",
        headers={"X-Worker-Authorization": token},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "executing"


async def test_minted_credential_authenticates_with_fallback_disabled(
    migrated_dsn: str,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The dispatch-minted credential works even with the shared fallback off.

    This is the new happy path proving per-execution auth stands on its own:
    the app is built with ``worker_shared_token_fallback_enabled=False``.
    """
    async with _capturing_app(migrated_dsn, fallback_enabled=False) as (
        client,
        dispatcher,
    ):
        ctx = await _setup(client, create_organization, session_factory)
        execution_id = (await _create_execution(client, ctx)).json()["id"]

        handoff = dispatcher.handoffs[0]
        assert handoff is not None
        token = handoff.raw_token.get_secret_value()

        started = await client.post(
            f"/api/v1/validation-executions/{execution_id}/worker-started",
            headers={"X-Worker-Authorization": token},
        )
        assert started.status_code == 200
        assert started.json()["status"] == "executing"

        # The shared token must NOT authenticate here — fallback is disabled.
        shared = await client.post(
            f"/api/v1/validation-executions/{execution_id}/worker-finished",
            json={"succeeded": True, "outcome": "validated"},
            headers={"X-Worker-Authorization": WORKER_AUTH_TOKEN},
        )
        assert shared.status_code == 401


# ---------------------------------------------------------------------------
# Failure / rollback
# ---------------------------------------------------------------------------


async def test_dispatch_failure_rolls_back_credential_with_execution(
    app_client: Callable[..., Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Fail-closed dispatcher: execution AND credential roll back together."""
    async with app_client(Environment.development) as client:
        ctx = await _setup(client, create_organization, session_factory)
        resp = await _create_execution(client, ctx)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "validation_dispatch_not_configured"

    # The credential was minted inside the same transaction, so it rolled back
    # with the execution — no orphaned grant survives.
    assert await _count_rows(session_factory, "validation_executions") == 0
    assert await _count_rows(session_factory, "validation_worker_credentials") == 0


async def test_credential_issuance_failure_prevents_dispatch(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If issuance is rejected, the execution is never dispatched or persisted."""
    client, dispatcher, _app = validation_app
    ctx = await _setup(client, create_organization, session_factory)

    async def _rejected_issue(self: Any, **_kwargs: Any) -> WorkerCredentialIssueResult:
        return WorkerCredentialIssueResult(
            outcome=WorkerCredentialIssueOutcome.rejected,
            failure="execution_not_issuable",
        )

    monkeypatch.setattr(PersistedWorkerCredentialIssuer, "issue", _rejected_issue)

    resp = await _create_execution(client, ctx)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "worker_credential_issuance_failed"

    # Dispatch was never reached, and the create transaction rolled back.
    assert dispatcher.dispatched == []
    assert await _count_rows(session_factory, "validation_executions") == 0
    assert await _count_rows(session_factory, "validation_worker_credentials") == 0
