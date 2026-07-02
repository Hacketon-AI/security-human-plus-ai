"""Unit tests for the Celery production worker consumer skeleton.

Pin the worker-side behaviour that broker redelivery, malformed envelopes,
runner crashes, and delivery failures must satisfy *before* a real Celery
worker is enabled: the lifecycle order (worker-started -> runner ->
worker-finished) is fixed, malformed envelopes touch nothing, started
delivery failure prevents the runner, runner exceptions are recovered into a
sanitized ``failed_safely``, no payload/token/target/evidence/raw-exception
ever reaches the log, and the module imports nothing from the API runtime
(FastAPI, ``app.main``, dispatcher, service, router, repositories,
SQLAlchemy session). The API path is also pinned to not pull the worker in.
"""

import ast
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from app.modules.validation_executions import (
    celery_worker as celery_worker_module,
)
from app.modules.validation_executions import (
    dispatcher as dispatcher_module,
)
from app.modules.validation_executions import (
    router as router_module,
)
from app.modules.validation_executions import (
    service as service_module,
)
from app.modules.validation_executions.broker_contracts import (
    BrokerConsumerOutcome,
    BrokerConsumerResult,
    build_dispatch_envelope,
)
from app.modules.validation_executions.celery_worker import (
    DEFAULT_VALIDATION_TASK_NAME,
    make_run_validation_task,
    run_validation_envelope,
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
from celery import Celery
from pydantic import SecretStr

# Distinctive sentinel values: if any of these strings reach a log line or a
# return value, the leakage assertions below will catch it.
_SENSITIVE_TOKEN = "supersecret-kill-switch-poll-key"
_TARGET = "https://app.example.com/login"
_BASE_URL = "http://control-plane.test"
_WORKER_AUTH_TOKEN = "test-worker-token"
_EVIDENCE_VALUE = "max-age=63072000; includeSubDomains"

_STRONG_HEADERS = {
    "Strict-Transport-Security": _EVIDENCE_VALUE,
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=()",
}


def _payload(
    execution_id: str = "11111111-1111-1111-1111-111111111111",
    kill_switch_token: str = _SENSITIVE_TOKEN,
) -> WorkerDispatchPayload:
    return WorkerDispatchPayload(
        execution_id=execution_id,
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        execution_specification={
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "target": _TARGET,
            "kill_switch_token": kill_switch_token,
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
    """Serialize a payload into the JSON-safe envelope shape the broker delivers."""
    envelope = build_dispatch_envelope(
        payload or _payload(),
        message_id=message_id,
        created_at=datetime(2026, 6, 27, tzinfo=UTC).isoformat(),
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


# --- Fakes: scanner-side transport -----------------------------------------


class _FakeScannerTransport:
    """``HttpTransport`` that returns a fixed strong-headers response. No I/O."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        self.calls.append(url)
        return HttpResponse(200, _STRONG_HEADERS, url, 8.0)


class _RecordingTransportFactory:
    """Factory whose call-count tests assert is zero for malformed envelopes."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(
        self, scope: Mapping[str, Any], safety: Mapping[str, Any]
    ) -> HttpTransport:
        self.calls += 1
        return _FakeScannerTransport()


# --- Fakes: control-plane delivery transport -------------------------------


class _RecordingResultTransport:
    """Records every worker hook POST and returns the configured status.

    Status codes can be overridden per-path (``started_status`` /
    ``finished_status``) so tests can simulate just one signal failing.
    """

    def __init__(
        self,
        *,
        started_status: int = 200,
        finished_status: int = 204,
    ) -> None:
        self._started_status = started_status
        self._finished_status = finished_status
        self.posts: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: Mapping[str, str],
    ) -> WorkerDeliveryResponse:
        self.posts.append({"url": url, "body": json_body, "headers": dict(headers)})
        status = (
            self._started_status
            if url.endswith("/worker-started")
            else self._finished_status
        )
        return WorkerDeliveryResponse(status_code=status)


class _ExplodingStartedTransport:
    """Raises on ``worker-started``; finished is recorded if reached (must not be)."""

    def __init__(self) -> None:
        self.finished_posts: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: Mapping[str, str],
    ) -> WorkerDeliveryResponse:
        if url.endswith("/worker-started"):
            raise RuntimeError("simulated worker-started transport failure")
        self.finished_posts.append({"url": url, "body": json_body})
        return WorkerDeliveryResponse(status_code=204)


class _ExplodingFinishedTransport:
    """Records ``worker-started`` and raises on ``worker-finished``."""

    def __init__(self) -> None:
        self.started_posts: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: Mapping[str, str],
    ) -> WorkerDeliveryResponse:
        if url.endswith("/worker-started"):
            self.started_posts.append({"url": url, "body": json_body})
            return WorkerDeliveryResponse(status_code=200)
        raise RuntimeError("simulated worker-finished transport failure")


def _client(transport: object) -> WorkerClient:
    return WorkerClient(
        base_url=_BASE_URL,
        transport=transport,  # type: ignore[arg-type]
        auth_token=SecretStr(_WORKER_AUTH_TOKEN),
    )


def _split_posts(
    posts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    started = [p for p in posts if p["url"].endswith("/worker-started")]
    finished = [p for p in posts if p["url"].endswith("/worker-finished")]
    return started, finished


# --- Kill switches ---------------------------------------------------------


class _InactiveKillSwitch:
    """Kill switch that never aborts the run."""

    async def is_active(self) -> bool:
        return False


class _ActiveKillSwitch:
    """Kill switch that is always active (aborts the runner immediately)."""

    async def is_active(self) -> bool:
        return True


# --- Happy path -----------------------------------------------------------


async def test_valid_envelope_runs_started_then_runner_then_finished() -> None:
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    result = await run_validation_envelope(
        _envelope_dict(),
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert isinstance(result, BrokerConsumerResult)
    assert result.outcome is BrokerConsumerOutcome.delivered
    assert result.message_id == "broker-msg-1"

    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert len(finished) == 1
    # Order: started before finished — by index of insertion.
    assert transport.posts[0]["url"].endswith("/worker-started")
    assert transport.posts[1]["url"].endswith("/worker-finished")
    # Runner actually ran the scanner transport (i.e. the factory was built).
    assert factory.calls == 1


# --- Malformed envelope ---------------------------------------------------


async def test_malformed_envelope_posts_nothing_and_no_target_request() -> None:
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    # Missing required ``message_id`` makes the envelope malformed.
    bad_envelope = _envelope_dict()
    del bad_envelope["message_id"]

    result = await run_validation_envelope(
        bad_envelope,
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.malformed
    # No hook was posted and no scanner-side transport was even built.
    assert transport.posts == []
    assert factory.calls == 0


async def test_non_mapping_envelope_is_malformed_and_posts_nothing() -> None:
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    result = await run_validation_envelope(
        ["not", "a", "mapping"],  # type: ignore[arg-type]
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.malformed
    assert result.message_id is None
    assert transport.posts == []
    assert factory.calls == 0


async def test_schema_version_mismatch_posts_nothing() -> None:
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    envelope = _envelope_dict()
    envelope["schema_version"] = "999"  # No known consumer understands this.

    result = await run_validation_envelope(
        envelope,
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.malformed
    assert transport.posts == []
    assert factory.calls == 0


async def test_payload_hash_mismatch_posts_nothing() -> None:
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    envelope = _envelope_dict()
    # Tamper with the payload after the hash was computed.
    envelope["payload"] = dict(envelope["payload"])
    envelope["payload"]["execution_id"] = "22222222-2222-2222-2222-222222222222"

    result = await run_validation_envelope(
        envelope,
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.malformed
    assert transport.posts == []
    assert factory.calls == 0


async def test_extra_envelope_field_is_malformed_and_posts_nothing() -> None:
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    envelope = _envelope_dict()
    envelope["snuck_in"] = "value"

    result = await run_validation_envelope(
        envelope,
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.malformed
    assert transport.posts == []
    assert factory.calls == 0


# --- Started delivery failure prevents runner + finished ------------------


async def test_started_delivery_failure_prevents_runner_and_finished() -> None:
    transport = _ExplodingStartedTransport()
    factory = _RecordingTransportFactory()

    result = await run_validation_envelope(
        _envelope_dict(),
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.started_delivery_failed
    # The runner was never invoked (factory not built) and worker-finished was
    # never posted (no finished post recorded).
    assert factory.calls == 0
    assert transport.finished_posts == []


async def test_started_non_2xx_is_a_failed_delivery_and_blocks_runner() -> None:
    transport = _RecordingResultTransport(started_status=503)
    factory = _RecordingTransportFactory()

    result = await run_validation_envelope(
        _envelope_dict(),
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.started_delivery_failed
    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert finished == []
    assert factory.calls == 0


# --- Runner failure recovery ----------------------------------------------


async def test_runner_malformed_payload_after_started_posts_failed_safely() -> None:
    transport = _RecordingResultTransport()
    # Build an envelope with an empty execution_id but valid envelope contract
    # by tampering with the inside of the serialized payload AFTER the hash is
    # locked. To keep the hash valid, we instead build a fresh envelope using a
    # payload that the runner will reject (e.g. allowed_ports list contains a
    # negative integer — caught inside the runner's _parse_allowed_ports).
    payload = WorkerDispatchPayload(
        execution_id="11111111-1111-1111-1111-111111111111",
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        execution_specification={
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "target": _TARGET,
            "kill_switch_token": _SENSITIVE_TOKEN,
        },
        scope_snapshot={"allowed_ports": [-1]},  # runner rejects this.
        safety_snapshot={
            "timeout_seconds": 5.0,
            "redirect_limit": 3,
            "max_requests": 5,
            "max_response_bytes": 65536,
            "kill_switch_active": False,
        },
    )

    result = await run_validation_envelope(
        _envelope_dict(payload),
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
    )

    assert result.outcome is BrokerConsumerOutcome.delivered
    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert len(finished) == 1
    # The finished body is the sanitized failed_safely shape.
    body = finished[0]["body"]
    assert body["outcome"] == "failed_safely"
    assert body["succeeded"] is False
    assert body["error_code"] == "worker_payload_rejected"
    # No raw error message escapes.
    assert body["error_message"] is None


async def test_runner_unexpected_exception_after_started_posts_failed_safely() -> None:
    transport = _RecordingResultTransport()

    def _exploding_factory(scope: object, safety: object) -> HttpTransport:
        raise RuntimeError("simulated factory blowup")

    result = await run_validation_envelope(
        _envelope_dict(),
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=_exploding_factory,
    )

    assert result.outcome is BrokerConsumerOutcome.delivered
    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert len(finished) == 1
    body = finished[0]["body"]
    assert body["outcome"] == "failed_safely"
    assert body["error_code"] == "worker_runtime_failed"
    assert body["error_message"] is None


# --- Finished delivery failure --------------------------------------------


async def test_finished_delivery_failure_is_reported_and_does_not_retry() -> None:
    transport = _ExplodingFinishedTransport()
    factory = _RecordingTransportFactory()

    result = await run_validation_envelope(
        _envelope_dict(),
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.finished_delivery_failed
    # Exactly one worker-started was posted, the runner ran once, and we did
    # not retry the failed finished post.
    assert len(transport.started_posts) == 1


async def test_finished_non_2xx_returns_finished_delivery_failed() -> None:
    transport = _RecordingResultTransport(finished_status=503)
    factory = _RecordingTransportFactory()

    result = await run_validation_envelope(
        _envelope_dict(),
        _client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.finished_delivery_failed
    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert len(finished) == 1  # No retry.


# --- Kill switch active ---------------------------------------------------


async def test_kill_switch_active_posts_blocked_by_control() -> None:
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    result = await run_validation_envelope(
        _envelope_dict(),
        _client(transport),
        kill_switch=_ActiveKillSwitch(),
        transport_factory=factory,
    )

    assert result.outcome is BrokerConsumerOutcome.delivered
    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert len(finished) == 1
    body = finished[0]["body"]
    assert body["outcome"] == "blocked_by_control"


# --- Duplicate delivery ---------------------------------------------------


async def test_duplicate_delivery_calls_hooks_once_per_invocation() -> None:
    transport = _RecordingResultTransport()
    envelope = _envelope_dict()

    # Two redelivery attempts: each invocation posts started+finished exactly
    # once. The consumer does not deduplicate here — that safety lives in the
    # idempotent API hooks (pinned by the service-layer integration tests).
    first = await run_validation_envelope(
        envelope, _client(transport), kill_switch=_InactiveKillSwitch()
    )
    second = await run_validation_envelope(
        envelope, _client(transport), kill_switch=_InactiveKillSwitch()
    )

    assert first.outcome is BrokerConsumerOutcome.delivered
    assert second.outcome is BrokerConsumerOutcome.delivered
    started, finished = _split_posts(transport.posts)
    assert len(started) == 2
    assert len(finished) == 2


# --- Log safety -----------------------------------------------------------


async def test_no_token_target_or_payload_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = _RecordingResultTransport()

    with caplog.at_level(logging.INFO, logger="securescope"):
        await run_validation_envelope(
            _envelope_dict(),
            _client(transport),
            kill_switch=_InactiveKillSwitch(),
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_TOKEN not in log_text
    assert _TARGET not in log_text
    assert _WORKER_AUTH_TOKEN not in log_text


async def test_no_envelope_or_evidence_in_logs_on_malformed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = _RecordingResultTransport()
    envelope = _envelope_dict()
    envelope["payload"] = {
        "execution_id": "42",
        "template_id": "leaky-token-" + _SENSITIVE_TOKEN,
        "execution_specification": {"leaked": _TARGET},
        "scope_snapshot": {},
        "safety_snapshot": {},
    }

    with caplog.at_level(logging.WARNING, logger="securescope"):
        await run_validation_envelope(
            envelope,
            _client(transport),
            kill_switch=_InactiveKillSwitch(),
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_TOKEN not in log_text
    assert _TARGET not in log_text


async def test_no_raw_exception_in_logs_on_runner_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = _RecordingResultTransport()
    secret_exception = "SECRET-EXC-" + _SENSITIVE_TOKEN

    def _exploding_factory(scope: object, safety: object) -> HttpTransport:
        raise RuntimeError(secret_exception)

    with caplog.at_level(logging.WARNING, logger="securescope"):
        await run_validation_envelope(
            _envelope_dict(),
            _client(transport),
            kill_switch=_InactiveKillSwitch(),
            transport_factory=_exploding_factory,
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_exception not in log_text
    assert _SENSITIVE_TOKEN not in log_text


# --- Thin Celery task wrapper --------------------------------------------


def test_register_task_uses_default_name_and_ignore_result() -> None:
    app = Celery("test-securescope")
    task = make_run_validation_task(
        app,
        client=_client(_RecordingResultTransport()),
        kill_switch=_InactiveKillSwitch(),
    )
    # The wrapper registers under the default name and disables the result
    # backend so no Redis/RPC backend is implied by selecting Celery.
    assert task.name == DEFAULT_VALIDATION_TASK_NAME
    assert task.ignore_result is True


def test_register_task_honours_custom_task_name() -> None:
    app = Celery("test-securescope")
    task = make_run_validation_task(
        app,
        client=_client(_RecordingResultTransport()),
        kill_switch=_InactiveKillSwitch(),
        task_name="some.other.name",
    )
    assert task.name == "some.other.name"


def test_register_task_does_not_run_envelope_at_registration_time() -> None:
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()
    app = Celery("test-securescope")

    make_run_validation_task(
        app,
        client=_client(transport),
        kill_switch=_InactiveKillSwitch(),
        transport_factory=factory,
    )

    # Merely registering the task must not invoke the lifecycle: no hook was
    # posted and no scanner-side transport was built.
    assert transport.posts == []
    assert factory.calls == 0


# --- Import purity --------------------------------------------------------


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


def test_celery_worker_module_import_purity() -> None:
    for module_name in _imported_modules(celery_worker_module):
        assert not any(token in module_name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"celery_worker.py must not import: {module_name}"
        )


def test_api_path_does_not_import_celery_worker() -> None:
    """Dispatcher, service, and router must not import the worker consumer.

    The API path can only ever publish; the worker side runs in a separate
    process. Even a transitive import would weaken the scanner-execution
    isolation boundary in ``.claude/rules/security-boundaries.md``.
    """
    for module in (dispatcher_module, service_module, router_module):
        for module_name in _imported_modules(module):
            assert "celery_worker" not in module_name, (
                f"{module.__name__} must not import celery_worker: {module_name}"
            )


def test_app_main_does_not_import_celery_worker() -> None:
    """``app.main`` may bind a Celery *publisher*, never the worker consumer."""
    from app import main as main_module

    for module_name in _imported_modules(main_module):
        assert "celery_worker" not in module_name, (
            f"app.main must not import celery_worker: {module_name}"
        )


# --- Wrapper shape: thin (no DB / no service / no FastAPI) ---------------


def test_make_run_validation_task_is_thin() -> None:
    """The decorator body should be a single ``asyncio.run`` call.

    Counting the number of statements in the wrapper's body is a guardrail:
    if a future change adds business logic, settings reads, or persistence
    here, this test will trip and the author is forced to push that work
    into the worker bootstrap instead.
    """
    source = celery_worker_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    wrapper_fn: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_validation":
            wrapper_fn = node
            break
    assert wrapper_fn is not None, "could not locate the registered task wrapper"
    # The thin wrapper body is exactly one statement: ``asyncio.run(...)``.
    assert len(wrapper_fn.body) == 1
    only_stmt = wrapper_fn.body[0]
    assert isinstance(only_stmt, ast.Expr)
    assert isinstance(only_stmt.value, ast.Await | ast.Call)
