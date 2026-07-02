"""Unit tests for the Step 4B worker bootstrap credential-injection boundary.

Pin the two new pieces without a broker or a database:

* The dev/test in-memory handoff registry resolves a raw token by execution
  id, consumes it once, expires it by wall clock, and never renders the
  token via repr/JSON/log.
* The worker bootstrap reads the *validated* execution id from the envelope,
  resolves the token from the side-channel (never the envelope), builds the
  worker client, and drives the started → runner → finished lifecycle — and
  fails closed (no worker-started, no target request) when the side-channel
  has no live credential.

Also pins the negative-space invariants: the broker envelope carries no raw
token / credential id, the shared-token fallback is off unless explicitly
passed, and the bootstrap module imports no API runtime.
"""

import ast
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.modules.validation_executions.broker_contracts import (
    BrokerConsumerOutcome,
    build_dispatch_envelope,
)
from app.modules.validation_executions.celery_worker_bootstrap import (
    run_validation_envelope_with_handoff,
)
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.executor_transport import (
    HttpResponse,
    HttpTransport,
)
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION
from app.modules.validation_executions.worker_client import (
    WorkerClient,
    WorkerDeliveryResponse,
)
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialHandoff,
    WorkerCredentialResolution,
    WorkerCredentialResolutionOutcome,
)
from app.modules.validation_executions.worker_credential_handoff_registry import (
    InMemoryWorkerCredentialHandoffRegistry,
)
from pydantic import SecretStr

_SENSITIVE_RAW_TOKEN = "side-channel-raw-token-never-log-me"
_EXECUTION_ID = "11111111-1111-1111-1111-111111111111"
_TARGET = "https://app.example.com/login"
_BASE_URL = "http://control-plane.test"
_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)

_STRONG_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=()",
}


class _FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _payload(execution_id: str = _EXECUTION_ID) -> WorkerDispatchPayload:
    return WorkerDispatchPayload(
        execution_id=execution_id,
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        execution_specification={
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "target": _TARGET,
            "kill_switch_token": "opaque-poll-key",
        },
        scope_snapshot={"allowed_ports": [443]},
        safety_snapshot={
            "timeout_seconds": 5.0,
            "redirect_limit": 3,
            "max_requests": 5,
            "max_response_bytes": 65536,
            "kill_switch_active": False,
        },
    )


def _envelope_dict(
    payload: WorkerDispatchPayload | None = None,
    *,
    message_id: str = "broker-msg-1",
) -> dict[str, Any]:
    envelope = build_dispatch_envelope(
        payload or _payload(),
        message_id=message_id,
        created_at=_NOW.isoformat(),
    )
    return {
        "message_id": envelope.message_id,
        "schema_version": envelope.schema_version,
        "payload": dict(envelope.payload),
        "payload_sha256": envelope.payload_sha256,
        "created_at": envelope.created_at,
        "attempt": envelope.attempt,
        "content_type": envelope.content_type,
    }


def _handoff(
    *,
    execution_id: str = _EXECUTION_ID,
    token: str = _SENSITIVE_RAW_TOKEN,
    expires_at: datetime | None = None,
) -> WorkerCredentialHandoff:
    return WorkerCredentialHandoff(
        execution_id=execution_id,
        credential_id="cred-1",
        raw_token=SecretStr(token),
        expires_at=expires_at or (_NOW + timedelta(minutes=30)),
    )


# --- Fakes ------------------------------------------------------------------


class _RecordingResultTransport:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: Mapping[str, str],
    ) -> WorkerDeliveryResponse:
        self.posts.append({"url": url, "body": json_body, "headers": dict(headers)})
        status = 200 if url.endswith("/worker-started") else 204
        return WorkerDeliveryResponse(status_code=status)


class _FakeScannerTransport:
    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        return HttpResponse(200, _STRONG_HEADERS, url, 8.0)


def _scanner_factory(scope: object, safety: object) -> HttpTransport:
    return _FakeScannerTransport()


class _CapturingClientFactory:
    """Builds a real WorkerClient over a recording transport, capturing the token."""

    def __init__(self) -> None:
        self.transport = _RecordingResultTransport()
        self.tokens_seen: list[str] = []
        self.calls = 0

    def __call__(self, raw_token: SecretStr) -> WorkerClient:
        self.calls += 1
        self.tokens_seen.append(raw_token.get_secret_value())
        return WorkerClient(
            base_url=_BASE_URL,
            transport=self.transport,  # type: ignore[arg-type]
            auth_token=raw_token,
        )


class _InactiveKillSwitch:
    async def is_active(self) -> bool:
        return False


class _AlwaysMissingSource:
    async def resolve(self, *, execution_id: str) -> WorkerCredentialResolution:
        return WorkerCredentialResolution(
            outcome=WorkerCredentialResolutionOutcome.missing
        )


class _UnavailableSource:
    async def resolve(self, *, execution_id: str) -> WorkerCredentialResolution:
        return WorkerCredentialResolution(
            outcome=WorkerCredentialResolutionOutcome.source_unavailable
        )


# --- Registry: resolve / consume-once / expiry ------------------------------


async def test_registry_resolves_registered_handoff() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff())

    resolution = await registry.resolve(execution_id=_EXECUTION_ID)

    assert resolution.outcome is WorkerCredentialResolutionOutcome.found
    assert resolution.raw_token is not None
    assert resolution.raw_token.get_secret_value() == _SENSITIVE_RAW_TOKEN


async def test_registry_consumes_handoff_once() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff())

    first = await registry.resolve(execution_id=_EXECUTION_ID)
    second = await registry.resolve(execution_id=_EXECUTION_ID)

    assert first.outcome is WorkerCredentialResolutionOutcome.found
    # Second read finds nothing — the handoff was consumed.
    assert second.outcome is WorkerCredentialResolutionOutcome.missing
    assert registry.size() == 0


async def test_registry_unknown_execution_is_missing() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    resolution = await registry.resolve(execution_id="unknown")
    assert resolution.outcome is WorkerCredentialResolutionOutcome.missing


async def test_registry_empty_id_is_invalid_reference() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    resolution = await registry.resolve(execution_id="")
    assert resolution.outcome is WorkerCredentialResolutionOutcome.invalid_reference


async def test_registry_expired_handoff_is_expired_and_dropped() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff(expires_at=_NOW - timedelta(seconds=1)))

    resolution = await registry.resolve(execution_id=_EXECUTION_ID)

    assert resolution.outcome is WorkerCredentialResolutionOutcome.expired
    assert resolution.raw_token is None
    # Dropped: a later resolve does not resurrect it.
    assert registry.size() == 0


def test_registry_does_not_expose_token_in_repr() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff())
    assert _SENSITIVE_RAW_TOKEN not in repr(registry)
    # The stored handoff's repr is also masked by SecretStr.
    assert _SENSITIVE_RAW_TOKEN not in repr(_handoff())


def test_registry_handoff_is_not_json_serializable() -> None:
    # A handoff carrying a SecretStr cannot be turned into JSON — a guard
    # against accidentally writing it to a broker/queue message.
    with pytest.raises(TypeError):
        json.dumps({"raw_token": _handoff().raw_token})


# --- Bootstrap: happy path --------------------------------------------------


async def test_bootstrap_resolves_token_and_runs_full_lifecycle() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff())
    factory = _CapturingClientFactory()

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=registry,
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
        transport_factory=_scanner_factory,
    )

    assert result.outcome is BrokerConsumerOutcome.delivered
    # The client was built with the side-channel token.
    assert factory.calls == 1
    assert factory.tokens_seen == [_SENSITIVE_RAW_TOKEN]
    # started then finished, in order.
    urls = [p["url"] for p in factory.transport.posts]
    assert urls[0].endswith("/worker-started")
    assert urls[1].endswith("/worker-finished")
    # The started POST carried the per-execution token in the auth header.
    started = factory.transport.posts[0]
    assert started["headers"]["X-Worker-Authorization"] == _SENSITIVE_RAW_TOKEN


# --- Bootstrap: fail-closed paths ------------------------------------------


async def test_bootstrap_fails_closed_when_credential_missing() -> None:
    factory = _CapturingClientFactory()

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=_AlwaysMissingSource(),
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
        transport_factory=_scanner_factory,
    )

    assert result.outcome is BrokerConsumerOutcome.started_delivery_failed
    # No client was built and no hook was posted — nothing ran.
    assert factory.calls == 0
    assert factory.transport.posts == []


async def test_bootstrap_fails_closed_when_source_unavailable() -> None:
    factory = _CapturingClientFactory()

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=_UnavailableSource(),
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
    )

    assert result.outcome is BrokerConsumerOutcome.started_delivery_failed
    assert factory.calls == 0


async def test_bootstrap_fails_closed_on_expired_handoff() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff(expires_at=_NOW - timedelta(seconds=1)))
    factory = _CapturingClientFactory()

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=registry,
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
    )

    assert result.outcome is BrokerConsumerOutcome.started_delivery_failed
    assert factory.calls == 0


async def test_bootstrap_rejects_malformed_envelope_before_lookup() -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff())
    factory = _CapturingClientFactory()
    bad = _envelope_dict()
    del bad["payload_sha256"]  # malformed envelope.

    result = await run_validation_envelope_with_handoff(
        bad,
        source=registry,
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
    )

    assert result.outcome is BrokerConsumerOutcome.malformed
    assert factory.calls == 0
    # The handoff was NOT consumed — no lookup happened.
    assert registry.size() == 1


async def test_bootstrap_wrong_execution_reference_fails_closed() -> None:
    # A handoff registered for a *different* execution than the envelope's.
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff(execution_id="99999999-9999-9999-9999-999999999999"))
    factory = _CapturingClientFactory()

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),  # execution _EXECUTION_ID
        source=registry,
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
    )

    assert result.outcome is BrokerConsumerOutcome.started_delivery_failed
    assert factory.calls == 0


# --- Shared-token fallback: off by default ---------------------------------


async def test_no_shared_token_fallback_by_default() -> None:
    factory = _CapturingClientFactory()
    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=_AlwaysMissingSource(),
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
    )
    # No fallback passed → missing credential is terminal.
    assert result.outcome is BrokerConsumerOutcome.started_delivery_failed
    assert factory.calls == 0


async def test_explicit_shared_token_fallback_is_used_when_source_misses() -> None:
    factory = _CapturingClientFactory()
    fallback = SecretStr("transitional-shared-token")

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=_AlwaysMissingSource(),
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
        transport_factory=_scanner_factory,
        shared_token_fallback=fallback,
    )

    assert result.outcome is BrokerConsumerOutcome.delivered
    assert factory.tokens_seen == ["transitional-shared-token"]


# --- Envelope carries no raw token / credential id -------------------------


def test_envelope_dict_has_no_credential_fields() -> None:
    envelope = _envelope_dict()
    flat = json.dumps(envelope)
    assert _SENSITIVE_RAW_TOKEN not in flat
    for forbidden in ("raw_token", "credential_id", "worker_token", "auth_token"):
        assert forbidden not in flat
    # The payload sub-dict is exactly the five contract fields.
    assert set(envelope["payload"].keys()) == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }


# --- Log safety -------------------------------------------------------------


async def test_no_raw_token_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    registry = InMemoryWorkerCredentialHandoffRegistry(_FixedClock(_NOW))
    registry.register(_handoff())
    factory = _CapturingClientFactory()

    with caplog.at_level(logging.INFO, logger="securescope"):
        await run_validation_envelope_with_handoff(
            _envelope_dict(),
            source=registry,
            client_factory=factory,
            kill_switch=_InactiveKillSwitch(),
            transport_factory=_scanner_factory,
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_RAW_TOKEN not in log_text


async def test_no_raw_token_in_logs_on_fail_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    factory = _CapturingClientFactory()
    with caplog.at_level(logging.WARNING, logger="securescope"):
        await run_validation_envelope_with_handoff(
            _envelope_dict(),
            source=_AlwaysMissingSource(),
            client_factory=factory,
            kill_switch=_InactiveKillSwitch(),
        )
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_RAW_TOKEN not in log_text


# --- Import purity ----------------------------------------------------------


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


def test_bootstrap_and_registry_import_purity() -> None:
    from app.modules.validation_executions import (
        celery_worker_bootstrap as bootstrap_module,
    )
    from app.modules.validation_executions import (
        worker_credential_handoff_registry as registry_module,
    )

    for module in (bootstrap_module, registry_module):
        for name in _imported_modules(module):
            assert not any(token in name for token in _FORBIDDEN_IMPORT_TOKENS), (
                f"{module.__name__} must not import {name}"
            )


def test_api_path_does_not_import_bootstrap() -> None:
    from app import main as main_module
    from app.modules.validation_executions import dispatcher as dispatcher_module
    from app.modules.validation_executions import router as router_module
    from app.modules.validation_executions import service as service_module

    for module in (main_module, dispatcher_module, service_module, router_module):
        for name in _imported_modules(module):
            assert "celery_worker_bootstrap" not in name, (
                f"{module.__name__} must not import the worker bootstrap: {name}"
            )
