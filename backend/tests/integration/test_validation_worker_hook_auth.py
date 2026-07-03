"""Step 3 — worker hook auth upgraded to per-execution credentials.

These integration tests pin the new ``worker_auth`` behaviour against a real
PostgreSQL: the hooks accept only a per-execution credential, the
transitional shared-token fallback is gated on an explicit Settings flag
(default off), every rejection mode collapses to the same 401, and the
worker-side response stays minimal. Existing hook-functional coverage stays
in ``test_validation_executions_api.py`` and continues to drive the shared
fallback (the ``validation_app`` fixture enables it for backwards
compatibility); Step-3-specific assertions live here.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.config import Environment, ValidationDispatcherBackend
from app.modules.validation_executions.credential_issuer import (
    PersistedWorkerCredentialIssuer,
)
from app.modules.validation_executions.credential_repository import (
    WorkerCredentialRepository,
)
from app.modules.validation_executions.models import ValidationExecution
from app.modules.validation_executions.repository import (
    ValidationExecutionRepository,
)
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerHookAction,
)
from app.platform.clock import SystemClock
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import (
    WORKER_AUTH_TOKEN,
    CapturingValidationDispatcher,
    tenant_headers,
)
from tests.integration.test_validation_executions_api import (
    _create_body,
    _setup,
)

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_execution(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, str], str]:
    """Build the full asset chain and POST one queued validation execution.

    Returns the setup context (org/project/asset/etc ids) plus the
    execution id of the freshly-queued row, ready for worker-* hooks.
    """
    ctx = await _setup(client, create_organization, session_factory)
    body = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx),
            headers=tenant_headers(ctx["org_id"]),
        )
    ).json()
    return ctx, body["id"]


async def _issue_credential(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    execution_id: str,
    actions: frozenset[WorkerHookAction],
    expires_at: datetime | None = None,
    issued_for_other_execution: bool = False,
) -> str:
    """Mint one per-execution credential and return the raw token string.

    The issuer runs in its own session so the row is committed before the
    HTTP request reaches the auth layer. ``issued_for_other_execution`` is
    used to construct deliberate cross-execution probes.
    """
    if expires_at is None:
        expires_at = datetime.now(tz=UTC) + timedelta(minutes=30)

    async with session_factory() as session:
        execution = (
            await session.execute(
                select(ValidationExecution).where(
                    ValidationExecution.id == execution_id
                )
            )
        ).scalar_one()
        issuer = PersistedWorkerCredentialIssuer(
            WorkerCredentialRepository(session),
            ValidationExecutionRepository(session),
            SystemClock(),
        )
        target_id = execution.id
        target_org = execution.organization_id
        result = await issuer.issue(
            execution_id=str(target_id)
            if not issued_for_other_execution
            else str(execution_id),
            organization_id=str(target_org),
            allowed_actions=actions,
            expires_at=expires_at,
        )
        await session.commit()

    assert result.issued is not None, result.failure
    return result.issued.raw_token.get_secret_value()


async def _revoke_credentials_for(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    execution_id: str,
) -> None:
    async with session_factory() as session:
        execution = (
            await session.execute(
                select(ValidationExecution).where(
                    ValidationExecution.id == execution_id
                )
            )
        ).scalar_one()
        repo = WorkerCredentialRepository(session)
        await repo.revoke_for_execution(
            execution.id,
            execution.organization_id,
            revoked_at=datetime.now(tz=UTC),
        )
        await session.commit()


def _bearer(token: str) -> dict[str, str]:
    return {"X-Worker-Authorization": token}


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


async def test_worker_started_succeeds_with_per_execution_credential(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    _ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )
    token = await _issue_credential(
        session_factory,
        execution_id=execution_id,
        actions=frozenset(
            {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
        ),
    )

    resp = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started",
        headers=_bearer(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "executing"
    assert body["started_at"] is not None
    # Worker response stays minimal: no spec/snapshot/evidence/kill_switch
    # token field is reflected back.
    for forbidden in (
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
        "kill_switch_token",
        "step_results",
    ):
        assert forbidden not in body
    # No X-Organization-Id was sent — auth derived the tenant from the
    # credential row alone.


async def test_worker_finished_succeeds_with_per_execution_credential(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    _ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )
    token = await _issue_credential(
        session_factory,
        execution_id=execution_id,
        actions=frozenset(
            {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
        ),
    )
    await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started",
        headers=_bearer(token),
    )

    resp = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-finished",
        json={"succeeded": True, "outcome": "validated"},
        headers=_bearer(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["finished_at"] is not None


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


async def test_missing_token_is_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    _ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )

    resp = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started"
    )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "worker_authentication_failed"


async def test_invalid_token_is_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    _ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )

    resp = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started",
        headers=_bearer("not-a-real-token-anywhere"),
    )

    assert resp.status_code == 401


async def test_credential_for_different_execution_is_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Same tenant, two executions: a credential for B must not unlock A.

    This is also the "different organization" probe in practice — every
    credential is bound to a single execution, which is in turn bound to a
    single tenant by foreign key, so an off-tenant credential is
    structurally identical to an off-execution credential. The verifier
    rejects with ``rejected_execution``; both surface to the caller as the
    same 401.
    """
    client, _dispatcher, _app = validation_app
    ctx, exec_a = await _create_execution(client, create_organization, session_factory)
    # Queue a second execution in the same tenant by reusing the asset chain
    # ``_setup`` already built; only the execution row differs.
    exec_b = (
        await client.post(
            "/api/v1/validation-executions",
            json=_create_body(ctx, idempotency_key="cross-exec-b"),
            headers=tenant_headers(ctx["org_id"]),
        )
    ).json()["id"]
    token_for_b = await _issue_credential(
        session_factory,
        execution_id=exec_b,
        actions=frozenset({WorkerHookAction.worker_started}),
    )

    # Present B's credential against A — must fail closed.
    resp = await client.post(
        f"/api/v1/validation-executions/{exec_a}/worker-started",
        headers=_bearer(token_for_b),
    )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "worker_authentication_failed"


async def test_credential_with_wrong_action_is_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    _ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )
    # ``worker_started`` is NOT in the allow-list.
    token = await _issue_credential(
        session_factory,
        execution_id=execution_id,
        actions=frozenset({WorkerHookAction.worker_finished}),
    )

    resp = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started",
        headers=_bearer(token),
    )

    assert resp.status_code == 401


async def test_expired_credential_is_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    _ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )
    # Issue with the shortest legal future expiry, then sleep past it.
    soon = datetime.now(tz=UTC) + timedelta(milliseconds=200)
    token = await _issue_credential(
        session_factory,
        execution_id=execution_id,
        actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=soon,
    )
    # Wait until after ``soon`` so the verifier sees ``now >= expires_at``.
    import asyncio

    await asyncio.sleep(0.3)

    resp = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started",
        headers=_bearer(token),
    )

    assert resp.status_code == 401


async def test_revoked_credential_is_rejected(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client, _dispatcher, _app = validation_app
    _ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )
    token = await _issue_credential(
        session_factory,
        execution_id=execution_id,
        actions=frozenset({WorkerHookAction.worker_started}),
    )
    await _revoke_credentials_for(session_factory, execution_id=execution_id)

    resp = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started",
        headers=_bearer(token),
    )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Shared-token fallback gate
# ---------------------------------------------------------------------------


async def test_shared_token_is_rejected_when_fallback_disabled(
    app_client: Callable[..., Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Default development app has fallback off; the shared token must 401.

    The ``in_memory`` dispatcher backend is enabled only so the execution can
    be created (the default production-shaped dispatcher fails closed by
    design); it does not touch the worker-auth path under test.
    """
    async with app_client(
        Environment.development,
        validation_dispatcher_backend=ValidationDispatcherBackend.in_memory,
    ) as client:
        _ctx, execution_id = await _create_execution(
            client, create_organization, session_factory
        )
        resp = await client.post(
            f"/api/v1/validation-executions/{execution_id}/worker-started",
            headers=_bearer(WORKER_AUTH_TOKEN),
        )

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "worker_authentication_failed"


async def test_shared_token_accepted_only_when_fallback_enabled(
    app_client: Callable[..., Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with app_client(
        Environment.development,
        worker_auth_token=SecretStr(WORKER_AUTH_TOKEN),
        worker_shared_token_fallback_enabled=True,
        validation_dispatcher_backend=ValidationDispatcherBackend.in_memory,
    ) as client:
        _ctx, execution_id = await _create_execution(
            client, create_organization, session_factory
        )
        resp = await client.post(
            f"/api/v1/validation-executions/{execution_id}/worker-started",
            headers=_bearer(WORKER_AUTH_TOKEN),
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "executing"


async def test_shared_token_fallback_logs_deprecation_but_not_token(
    app_client: Callable[..., Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the shape of the deprecation warning the auth layer emits.

    Direct logger capture is fragile when earlier tests in the session
    have touched the parent logger hierarchy. Instead, monkeypatch the
    module-level ``_logger`` with a tiny recorder so the assertion is
    independent of pytest caplog state or Python's effective-level
    resolution. We assert: the warning fires once on the fallback path,
    its format string never names the token value, and the formatted
    args never contain it either.
    """
    from app.modules.validation_executions import worker_auth as worker_auth_module

    calls: list[tuple[str, tuple[Any, ...]]] = []

    class _RecorderLogger:
        def warning(self, fmt: str, *args: Any) -> None:
            calls.append((fmt, args))

        # Unused on this path, but the dependency may emit info/debug
        # elsewhere; keep silent no-ops so we never raise.
        def info(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
            pass

        def debug(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
            pass

    monkeypatch.setattr(worker_auth_module, "_logger", _RecorderLogger())

    async with app_client(
        Environment.development,
        worker_auth_token=SecretStr(WORKER_AUTH_TOKEN),
        worker_shared_token_fallback_enabled=True,
        validation_dispatcher_backend=ValidationDispatcherBackend.in_memory,
    ) as client:
        _ctx, execution_id = await _create_execution(
            client, create_organization, session_factory
        )
        resp = await client.post(
            f"/api/v1/validation-executions/{execution_id}/worker-started",
            headers=_bearer(WORKER_AUTH_TOKEN),
        )
        # Sanity: the fallback path must have authenticated — otherwise the
        # deprecation warning would never fire.
        assert resp.status_code == 200, resp.text

    deprecation_calls = [c for c in calls if "deprecated" in c[0].lower()]
    assert deprecation_calls, f"expected a deprecation warning, got {calls!r}"
    # Format string never embeds the token literal; neither do the args.
    fmt, args = deprecation_calls[0]
    assert WORKER_AUTH_TOKEN not in fmt
    for arg in args:
        assert WORKER_AUTH_TOKEN not in str(arg)


# ---------------------------------------------------------------------------
# Idempotency + leakage
# ---------------------------------------------------------------------------


async def test_terminal_worker_finished_revokes_credential_and_freezes_verdict(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A successful finish revokes the credential; a redelivery cannot revive it.

    The first ``worker-finished`` reaches a terminal verdict and — per the
    per-execution credential design (Expiry and revocation) — revokes the
    credential inside the same transaction. A broker redelivery therefore fails
    authentication with the single indistinguishable 401 (the revoked credential
    is no longer accepted), rather than re-entering the service. This is the
    intended fall-through: the recorded verdict is frozen, so the redelivery is
    harmless (the consumer does not retry a 401), and the credential cannot be
    replayed against the closed execution.
    """
    client, _dispatcher, _app = validation_app
    ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )
    token = await _issue_credential(
        session_factory,
        execution_id=execution_id,
        actions=frozenset(
            {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
        ),
    )
    await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-started",
        headers=_bearer(token),
    )
    body = {"succeeded": True, "outcome": "validated"}
    first = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-finished",
        json=body,
        headers=_bearer(token),
    )
    second = await client.post(
        f"/api/v1/validation-executions/{execution_id}/worker-finished",
        json=body,
        headers=_bearer(token),
    )

    assert first.status_code == 200
    # Terminal transition revoked the credential: the redelivered finish now
    # collapses to the single indistinguishable auth failure.
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "worker_authentication_failed"

    # The recorded verdict is frozen: the tenant-facing view still shows the
    # first (and only) terminal result, unmoved by the rejected redelivery.
    stored = (
        await client.get(
            f"/api/v1/validation-executions/{execution_id}",
            headers=tenant_headers(ctx["org_id"]),
        )
    ).json()
    assert stored["status"] == "succeeded"
    assert stored["outcome"] == "validated"
    assert stored["finished_at"] == first.json()["finished_at"]


async def test_no_raw_token_in_logs_on_per_execution_auth(
    validation_app: tuple[AsyncClient, CapturingValidationDispatcher, Any],
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _dispatcher, _app = validation_app
    _ctx, execution_id = await _create_execution(
        client, create_organization, session_factory
    )
    token = await _issue_credential(
        session_factory,
        execution_id=execution_id,
        actions=frozenset({WorkerHookAction.worker_started}),
    )

    with caplog.at_level(logging.INFO, logger="securescope"):
        await client.post(
            f"/api/v1/validation-executions/{execution_id}/worker-started",
            headers=_bearer(token),
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in log_text
