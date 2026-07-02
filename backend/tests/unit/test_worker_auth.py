"""Unit tests for worker transition authentication (Step 3).

Pin the parts of ``require_worker_started_context`` /
``require_worker_finished_context`` that integration tests cannot easily
assert: every failure mode collapses to the same indistinguishable
:class:`WorkerAuthenticationFailed`, the shared-token fallback gate is
off by default, the gate is honoured when on, and neither the configured
nor the presented token reaches the log. The full per-execution
credential happy path + DB-backed rejection branches are covered by the
PostgreSQL integration suite in
``tests/integration/test_validation_worker_hook_auth.py``.

A tiny in-memory fake session stands in for an ``AsyncSession``: the
auth dependency only uses it through ``WorkerCredentialRepository``,
which only calls ``session.execute(select(...))``. The fake returns
``None`` for every digest lookup, so the per-execution path always
misses and the shared-token branch is the part under test.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from app.config import Environment, Settings
from app.modules.validation_executions.worker_auth import (
    WorkerAuthenticationFailed,
    WorkerContext,
    require_worker_started_context,
)
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerHookAction,
)
from app.platform.clock import Clock
from pydantic import SecretStr

_CONFIGURED = "configured-worker-token"
_PRESENTED_SECRET = "presented-secret-token-do-not-log"


class _AlwaysMissSession:
    """Async-session stand-in that makes every credential lookup miss.

    The repository's ``get_by_token_digest`` issues a
    ``select(ValidationWorkerCredential).where(token_digest == ?)``.
    Returning a result whose ``scalar_one_or_none()`` is ``None`` is
    equivalent to "no row matched the digest", so the auth dependency
    proceeds to the shared-token branch — exactly the surface under
    test here.
    """

    async def execute(self, _statement: Any) -> "_AlwaysMissSession":
        return self

    def scalar_one_or_none(self) -> None:
        return None


class _FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _settings(
    *,
    token: str | None,
    fallback_enabled: bool,
) -> Settings:
    return Settings(
        environment=Environment.test,
        database_dsn=SecretStr("postgresql+asyncpg://u:p@localhost/db"),
        worker_auth_token=SecretStr(token) if token is not None else None,
        worker_shared_token_fallback_enabled=fallback_enabled,
    )


async def _call(
    *,
    execution_id: UUID,
    presented: str | None,
    token: str | None,
    fallback_enabled: bool,
) -> WorkerContext:
    return await require_worker_started_context(
        execution_id=execution_id,
        x_worker_authorization=presented,
        session=cast("Any", _AlwaysMissSession()),
        settings=_settings(token=token, fallback_enabled=fallback_enabled),
        clock=cast("Clock", _FixedClock(datetime(2026, 6, 27, tzinfo=UTC))),
    )


# --- Default fallback off: shared token alone is rejected -------------------


async def test_shared_token_is_rejected_when_fallback_disabled_by_default() -> None:
    """Default Settings has fallback off; the shared token must 401."""
    with pytest.raises(WorkerAuthenticationFailed):
        await _call(
            execution_id=uuid4(),
            presented=_CONFIGURED,
            token=_CONFIGURED,
            fallback_enabled=False,
        )


# --- Shared-token fallback (enabled) accepts the configured token only ------


async def test_shared_token_accepts_when_fallback_enabled_and_matches() -> None:
    execution_id = uuid4()
    context = await _call(
        execution_id=execution_id,
        presented=_CONFIGURED,
        token=_CONFIGURED,
        fallback_enabled=True,
    )
    # Authenticated as the fallback identity — bound to the path
    # ``execution_id`` and the requested action, no per-credential id.
    assert isinstance(context, WorkerContext)
    assert context.execution_id == execution_id
    assert context.action is WorkerHookAction.worker_started
    assert context.credential_id is None
    assert context.organization_id is None
    assert context.worker_reference == "shared-token-fallback"


# --- Every failure mode collapses to the same indistinguishable error -------


async def test_failure_modes_are_indistinguishable() -> None:
    """Missing, wrong-token, unconfigured, and fallback-disabled all 401."""
    settings_with_fallback = {
        "fallback_enabled": True,
        "token": _CONFIGURED,
    }
    cases: list[tuple[str | None, dict[str, Any]]] = [
        # Missing header.
        (None, settings_with_fallback),
        # Wrong shared token.
        ("wrong-token", settings_with_fallback),
        # Right shared token but no token configured.
        (_CONFIGURED, {"fallback_enabled": True, "token": None}),
        # Right shared token but fallback disabled.
        (_CONFIGURED, {"fallback_enabled": False, "token": _CONFIGURED}),
    ]
    messages: set[str] = set()
    codes: set[str] = set()
    for presented, settings_kwargs in cases:
        with pytest.raises(WorkerAuthenticationFailed) as exc_info:
            await _call(execution_id=uuid4(), presented=presented, **settings_kwargs)
        messages.add(str(exc_info.value))
        codes.add(exc_info.value.code)
    assert len(messages) == 1
    assert codes == {"worker_authentication_failed"}


# --- No token (configured or presented) reaches the log ---------------------


async def test_no_token_value_reaches_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both a successful fallback acceptance and a rejected attempt must
    leave the configured and presented token strings out of the logs.
    """
    with caplog.at_level(logging.DEBUG, logger="securescope"):
        await _call(
            execution_id=uuid4(),
            presented=_CONFIGURED,
            token=_CONFIGURED,
            fallback_enabled=True,
        )
        with pytest.raises(WorkerAuthenticationFailed):
            await _call(
                execution_id=uuid4(),
                presented=_PRESENTED_SECRET,
                token=_CONFIGURED,
                fallback_enabled=True,
            )
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _CONFIGURED not in log_text
    assert _PRESENTED_SECRET not in log_text
