"""Unit tests for the production container-env worker credential source.

Pin the production :class:`WorkerBootstrapSecretSource` (design Option 1,
container-env) without a broker, a database, or real process env mutation: an
explicit ``env`` mapping and a ``_FixedClock`` are injected. The source must

* return the token only when a complete, live, correctly-scoped env is present,
* consume the credential once (a redelivery in-process cannot re-read it),
* fail closed on every other case with a typed outcome and no token,
* never render the token via repr or a log line,

and it must drop into the *real* worker bootstrap unchanged, proving it is a
behavioural replacement for the dev in-memory registry behind the same Protocol.
"""

import ast
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.validation_executions.broker_contracts import (
    BrokerConsumerOutcome,
)
from app.modules.validation_executions.celery_worker_bootstrap import (
    run_validation_envelope_with_handoff,
)
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialResolutionOutcome,
)
from app.modules.validation_executions.worker_credential_env_source import (
    ENV_EXECUTION_ID,
    ENV_EXPIRES_AT,
    ENV_TOKEN,
    EnvironmentWorkerCredentialSource,
)

# Reuse the bootstrap test's fakes so the end-to-end test drives the real
# lifecycle without re-implementing a client/transport.
from tests.unit.test_validation_worker_bootstrap import (
    _CapturingClientFactory,
    _envelope_dict,
    _InactiveKillSwitch,
    _scanner_factory,
)

_SENSITIVE_RAW_TOKEN = "container-env-raw-token-never-log-me"
_EXECUTION_ID = "11111111-1111-1111-1111-111111111111"
_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


class _FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _env(
    *,
    token: str = _SENSITIVE_RAW_TOKEN,
    execution_id: str = _EXECUTION_ID,
    expires_at: datetime | None = None,
) -> dict[str, str]:
    return {
        ENV_TOKEN: token,
        ENV_EXECUTION_ID: execution_id,
        ENV_EXPIRES_AT: (expires_at or (_NOW + timedelta(minutes=30))).isoformat(),
    }


def _source(env: Mapping[str, str]) -> EnvironmentWorkerCredentialSource:
    return EnvironmentWorkerCredentialSource(_FixedClock(_NOW), env=env)


# --- found / consume-once ---------------------------------------------------


async def test_resolves_token_from_complete_env() -> None:
    source = _source(_env())

    resolution = await source.resolve(execution_id=_EXECUTION_ID)

    assert resolution.outcome is WorkerCredentialResolutionOutcome.found
    assert resolution.raw_token is not None
    assert resolution.raw_token.get_secret_value() == _SENSITIVE_RAW_TOKEN
    assert resolution.expires_at == _NOW + timedelta(minutes=30)


async def test_credential_is_consumed_once() -> None:
    source = _source(_env())

    first = await source.resolve(execution_id=_EXECUTION_ID)
    second = await source.resolve(execution_id=_EXECUTION_ID)

    assert first.outcome is WorkerCredentialResolutionOutcome.found
    # A redelivered message in the same process cannot re-read the token.
    assert second.outcome is WorkerCredentialResolutionOutcome.missing
    assert second.raw_token is None


# --- fail-closed paths ------------------------------------------------------


async def test_empty_requested_id_is_invalid_reference() -> None:
    source = _source(_env())
    resolution = await source.resolve(execution_id="")
    assert resolution.outcome is WorkerCredentialResolutionOutcome.invalid_reference
    assert resolution.raw_token is None


@pytest.mark.parametrize("missing_var", [ENV_TOKEN, ENV_EXECUTION_ID, ENV_EXPIRES_AT])
async def test_missing_required_var_is_missing(missing_var: str) -> None:
    env = _env()
    del env[missing_var]
    source = _source(env)

    resolution = await source.resolve(execution_id=_EXECUTION_ID)

    assert resolution.outcome is WorkerCredentialResolutionOutcome.missing
    assert resolution.raw_token is None


@pytest.mark.parametrize("blank_var", [ENV_TOKEN, ENV_EXECUTION_ID, ENV_EXPIRES_AT])
async def test_blank_required_var_is_missing(blank_var: str) -> None:
    env = _env()
    env[blank_var] = "   "
    source = _source(env)

    resolution = await source.resolve(execution_id=_EXECUTION_ID)

    assert resolution.outcome is WorkerCredentialResolutionOutcome.missing
    assert resolution.raw_token is None


async def test_env_scoped_to_other_execution_is_missing() -> None:
    # The container's secret is for a different execution than the request.
    source = _source(_env(execution_id="99999999-9999-9999-9999-999999999999"))

    resolution = await source.resolve(execution_id=_EXECUTION_ID)

    # Fail closed — never hand a mismatched token to the client.
    assert resolution.outcome is WorkerCredentialResolutionOutcome.missing
    assert resolution.raw_token is None


async def test_request_for_different_execution_than_container_is_missing() -> None:
    source = _source(_env())  # container scoped to _EXECUTION_ID

    resolution = await source.resolve(
        execution_id="22222222-2222-2222-2222-222222222222"
    )

    assert resolution.outcome is WorkerCredentialResolutionOutcome.missing
    assert resolution.raw_token is None


async def test_expired_credential_is_expired_and_consumed() -> None:
    source = _source(_env(expires_at=_NOW - timedelta(seconds=1)))

    resolution = await source.resolve(execution_id=_EXECUTION_ID)

    assert resolution.outcome is WorkerCredentialResolutionOutcome.expired
    assert resolution.raw_token is None
    # Consumed: a retry in-process does not resurrect it.
    again = await source.resolve(execution_id=_EXECUTION_ID)
    assert again.outcome is WorkerCredentialResolutionOutcome.missing


async def test_expiry_at_exact_instant_is_expired() -> None:
    # Expiry is exclusive: now == expires_at is already dead.
    source = _source(_env(expires_at=_NOW))
    resolution = await source.resolve(execution_id=_EXECUTION_ID)
    assert resolution.outcome is WorkerCredentialResolutionOutcome.expired


async def test_unparseable_expiry_is_source_unavailable() -> None:
    env = _env()
    env[ENV_EXPIRES_AT] = "not-a-timestamp"
    source = _source(env)

    resolution = await source.resolve(execution_id=_EXECUTION_ID)

    assert resolution.outcome is WorkerCredentialResolutionOutcome.source_unavailable
    assert resolution.raw_token is None


async def test_naive_expiry_is_source_unavailable() -> None:
    # A timezone-naive expiry is rejected rather than assumed-UTC, which could
    # otherwise extend validity past the real deadline.
    env = _env()
    env[ENV_EXPIRES_AT] = "2026-06-27T12:30:00"  # no tzinfo
    source = _source(env)

    resolution = await source.resolve(execution_id=_EXECUTION_ID)

    assert resolution.outcome is WorkerCredentialResolutionOutcome.source_unavailable
    assert resolution.raw_token is None


# --- token non-leakage ------------------------------------------------------


def test_token_not_in_repr() -> None:
    source = _source(_env())
    assert _SENSITIVE_RAW_TOKEN not in repr(source)


async def test_token_not_in_logs_on_found(caplog: pytest.LogCaptureFixture) -> None:
    source = _source(_env())
    with caplog.at_level(logging.INFO, logger="securescope"):
        await source.resolve(execution_id=_EXECUTION_ID)
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_RAW_TOKEN not in log_text


async def test_token_not_in_logs_on_fail_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A scoped-to-other-execution env still logs a warning; the token stays out.
    source = _source(_env(execution_id="99999999-9999-9999-9999-999999999999"))
    with caplog.at_level(logging.WARNING, logger="securescope"):
        await source.resolve(execution_id=_EXECUTION_ID)
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_RAW_TOKEN not in log_text


# --- end-to-end: drop-in behind the real bootstrap --------------------------


async def test_source_drives_full_lifecycle_via_bootstrap() -> None:
    """The env source is a behavioural replacement for the dev registry.

    Feeding it straight into the tested worker bootstrap runs the full
    started → finished lifecycle and builds the worker client with the env
    token — the whole point of the shared Protocol.
    """
    source = _source(_env())
    factory = _CapturingClientFactory()

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=source,
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
        transport_factory=_scanner_factory,
    )

    assert result.outcome is BrokerConsumerOutcome.delivered
    assert factory.calls == 1
    assert factory.tokens_seen == [_SENSITIVE_RAW_TOKEN]
    urls = [p["url"] for p in factory.transport.posts]
    assert urls[0].endswith("/worker-started")
    assert urls[1].endswith("/worker-finished")


async def test_bootstrap_fails_closed_when_env_absent() -> None:
    # An empty env → missing → the bootstrap never authenticates, nothing runs.
    source = EnvironmentWorkerCredentialSource(_FixedClock(_NOW), env={})
    factory = _CapturingClientFactory()

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=source,
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
    )

    assert result.outcome is BrokerConsumerOutcome.started_delivery_failed
    assert factory.calls == 0
    assert factory.transport.posts == []


# --- import purity ----------------------------------------------------------


_FORBIDDEN_IMPORT_TOKENS = (
    "fastapi",
    "sqlalchemy",
    "app.main",
    "platform.database",
    "platform.dependencies",
    "repository",
    "service",
    "router",
    "dispatcher",
    "celery",
)


def _imported_modules(module: object) -> list[str]:
    source = module.__file__  # type: ignore[attr-defined]
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_env_source_import_purity() -> None:
    from app.modules.validation_executions import (
        worker_credential_env_source as env_source_module,
    )

    for name in _imported_modules(env_source_module):
        assert not any(token in name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"{env_source_module.__name__} must not import {name}"
        )
