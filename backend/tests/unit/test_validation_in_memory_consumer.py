"""Unit tests for the dev-only in-memory dispatch consumer.

Pin the consumer's safe shape so it cannot drift into a production worker:
the full lifecycle (worker-started → runner → worker-finished) is driven in a
fixed order, a malformed message posts nothing, worker-started is required
before the runner runs, a runner exception never posts worker-finished, a
non-2xx delivery is not retried, logs carry no payload/token/snapshot, and
the module imports no FastAPI / SQLAlchemy / repository / service / router /
dispatcher / ``app.main``. The API path also stays clean of any consumer
import — the create-execution path only enqueues.
"""

import ast
import logging
from collections.abc import Mapping
from typing import Any

import pytest
from app.modules.validation_executions import (
    dispatcher as dispatcher_module,
)
from app.modules.validation_executions import (
    in_memory_consumer as in_memory_consumer_module,
)
from app.modules.validation_executions import (
    router as router_module,
)
from app.modules.validation_executions import (
    service as service_module,
)
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.dispatch_serialization import (
    serialize_worker_dispatch_payload,
)
from app.modules.validation_executions.enums import ExecutionOutcome
from app.modules.validation_executions.executor import KillSwitch
from app.modules.validation_executions.executor_transport import (
    HttpResponse,
    HttpTransport,
)
from app.modules.validation_executions.in_memory_consumer import (
    ConsumerOutcome,
    ConsumerResult,
    consume_available,
    consume_once,
)
from app.modules.validation_executions.in_memory_queue import (
    InMemoryDispatchQueue,
    QueuedDispatchMessage,
)
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION
from app.modules.validation_executions.worker_client import (
    WorkerClient,
    WorkerDeliveryResponse,
)
from app.modules.validation_executions.worker_runner import MalformedWorkerInput

_SENSITIVE_TOKEN = "supersecret-kill-switch-poll-key"
_TARGET = "https://app.example.com/login"
_BASE_URL = "http://control-plane.test"

_STRONG_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000",
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


# --- Fakes: scanner-side transport -----------------------------------------


class _FakeTransport:
    """In-memory ``HttpTransport`` that returns a fixed strong-headers response."""

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
    """Factory that records every call so tests can assert it was *not* built."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(
        self, scope: Mapping[str, Any], safety: Mapping[str, Any]
    ) -> HttpTransport:
        self.calls += 1
        return _FakeTransport()


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


class _ExplodingResultTransport:
    """Transport that always raises, simulating a network error on every POST."""

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: Mapping[str, str],
    ) -> WorkerDeliveryResponse:
        raise RuntimeError("simulated transport failure")


class _StartedExplodingTransport:
    """Raises only on ``worker-started``; finished would succeed if reached."""

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


def _client(transport: object) -> WorkerClient:
    from pydantic import SecretStr

    return WorkerClient(
        base_url=_BASE_URL,
        transport=transport,  # type: ignore[arg-type]
        auth_token=SecretStr("test-worker-token"),
    )


def _split_posts(
    posts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    started = [p for p in posts if p["url"].endswith("/worker-started")]
    finished = [p for p in posts if p["url"].endswith("/worker-finished")]
    return started, finished


# --- consume_once: empty queue ---------------------------------------------


async def test_consume_once_returns_no_message_when_queue_empty() -> None:
    queue = InMemoryDispatchQueue()
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert isinstance(result, ConsumerResult)
    assert result.outcome is ConsumerOutcome.no_message
    assert result.message_id is None
    assert result.started_delivery is None
    assert result.finished_delivery is None
    # No worker was run and no signal was posted.
    assert factory.calls == 0
    assert transport.posts == []


# --- consume_once: happy path posts started then finished exactly once -----


async def test_consume_once_posts_started_then_finished_exactly_once() -> None:
    queue = InMemoryDispatchQueue()
    message_id = queue.enqueue(_payload())
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.delivered
    assert result.message_id == message_id
    assert result.started_delivery is not None and result.started_delivery.delivered
    assert result.finished_delivery is not None and result.finished_delivery.delivered

    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert len(finished) == 1
    # Delivery order: worker-started first, worker-finished second.
    assert transport.posts[0]["url"].endswith("/worker-started")
    assert transport.posts[1]["url"].endswith("/worker-finished")
    # Scanner transport built exactly once (one message → one run).
    assert factory.calls == 1
    # The delivery transport receives the sanitized WorkerFinishedRequest body —
    # never the raw spec, snapshots, or kill-switch token.
    body = finished[0]["body"]
    assert "kill_switch_token" not in str(body)
    assert "execution_specification" not in body
    assert "scope_snapshot" not in body
    # And the queue is empty after one consume_once.
    assert queue.size() == 0


async def test_consume_once_started_uses_worker_auth_header_and_no_tenant_header() -> (
    None
):
    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    await consume_once(queue, _client(transport), transport_factory=factory)

    started, _ = _split_posts(transport.posts)
    headers = started[0]["headers"]
    # Worker hooks are machine-authenticated by the dedicated header only —
    # never via the tenant X-Organization-Id header.
    assert headers["X-Worker-Authorization"] == "test-worker-token"
    assert "X-Organization-Id" not in headers


async def test_consume_once_started_url_encodes_execution_id() -> None:
    queue = InMemoryDispatchQueue()
    # An execution id containing characters that would otherwise alter the URL
    # structure — the WorkerClient percent-encodes it as one path segment.
    weird_id = "weird id/../x"
    queue.enqueue(_payload(execution_id=weird_id))
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    await consume_once(queue, _client(transport), transport_factory=factory)

    started, _ = _split_posts(transport.posts)
    expected = (
        f"{_BASE_URL}/api/v1/validation-executions/weird%20id%2F..%2Fx/worker-started"
    )
    assert started[0]["url"] == expected
    assert " " not in started[0]["url"]
    assert "/../" not in started[0]["url"]


# --- worker-started failure short-circuits ---------------------------------


async def test_worker_started_rejection_prevents_runner_and_finished() -> None:
    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _RecordingResultTransport(started_status=409)
    factory = _RecordingTransportFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.started_delivery_failed
    assert result.started_delivery is not None
    assert result.started_delivery.delivered is False
    assert result.started_delivery.status_code == 409
    assert result.finished_delivery is None
    # Critical: no scanner transport was built, and no worker-finished was posted.
    assert factory.calls == 0
    _, finished = _split_posts(transport.posts)
    assert finished == []


async def test_worker_started_transport_error_prevents_runner_and_finished() -> None:
    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _StartedExplodingTransport()
    factory = _RecordingTransportFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.started_delivery_failed
    # The runner never ran and worker-finished was never attempted.
    assert factory.calls == 0
    assert transport.finished_posts == []


# --- consume_once: malformed message posts nothing -------------------------


async def test_serialization_malformed_message_posts_nothing() -> None:
    """A malformed queued dict fails deserialization; *no* signal is posted."""
    queue = InMemoryDispatchQueue()
    queue._items.append(
        QueuedDispatchMessage(
            message_id="bad-1",
            message={"execution_id": "x"},  # missing fields
        )
    )
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.malformed
    assert result.message_id == "bad-1"
    assert result.started_delivery is None
    assert result.finished_delivery is None
    # Critical: no worker-started, no scanner transport, no worker-finished.
    assert transport.posts == []
    assert factory.calls == 0


# --- runner rejection after started: worker_failed, no finished post -------


async def test_runner_malformed_payload_recovers_into_failed_safely_finished() -> None:
    """Payload deserializes but the runner refuses it after worker-started.

    The runner raises ``MalformedWorkerInput`` before any transport is built,
    so no target request is sent. To prevent the row from lingering in
    ``executing``, the consumer recovers into a sanitized ``failed_safely``
    :class:`WorkerFinishedRequest` and posts it through worker-finished —
    with ``error_code='worker_payload_rejected'`` and
    ``error_message=None``.
    """
    queue = InMemoryDispatchQueue()
    bad_payload = WorkerDispatchPayload(
        execution_id="33333333-3333-3333-3333-333333333333",
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        # execution_specification missing the required ``target`` field.
        execution_specification={
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "kill_switch_token": "k",
        },
        scope_snapshot={"allowed_ports": [443]},
        safety_snapshot={
            "timeout_seconds": 5.0,
            "redirect_limit": 3,
            "max_requests": 5,
            "max_response_bytes": 65536,
        },
    )
    queue._items.append(
        QueuedDispatchMessage(
            message_id="bad-2",
            message=serialize_worker_dispatch_payload(bad_payload),
        )
    )
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.delivered
    assert result.started_delivery is not None and result.started_delivery.delivered
    assert result.finished_delivery is not None and result.finished_delivery.delivered
    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert len(finished) == 1
    body = finished[0]["body"]
    assert body["succeeded"] is False
    assert body["outcome"] == ExecutionOutcome.failed_safely.value
    assert body["error_code"] == "worker_payload_rejected"
    assert body["error_message"] is None
    # No scanner transport was built — the runner raised before any network.
    assert factory.calls == 0


def test_runner_rejects_missing_target_at_validation_time() -> None:
    # Sanity check: the runner's own validation is what catches the case
    # above. Pinning it here documents the dependency the consumer relies on.
    from app.modules.validation_executions.dispatch_serialization import to_worker_input
    from app.modules.validation_executions.worker_runner import _validate_payload

    bad = WorkerDispatchPayload(
        execution_id="x",
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        execution_specification={"template_id": HTTP_SECURITY_HEADER_VALIDATION},
        scope_snapshot={},
        safety_snapshot={
            "timeout_seconds": 1.0,
            "redirect_limit": 1,
            "max_requests": 1,
            "max_response_bytes": 1024,
        },
    )

    with pytest.raises(MalformedWorkerInput):
        _validate_payload(to_worker_input(bad))


# --- worker runner exception is reported safely ----------------------------


async def test_worker_runner_exception_recovers_into_failed_safely_finished() -> None:
    """A runtime crash inside the runner is recovered into ``failed_safely``.

    The runner exception is caught, a sanitized ``failed_safely``
    :class:`WorkerFinishedRequest` is built, and ``worker-finished`` is
    posted so the execution does not linger in ``executing``. The raw
    exception is *not* logged, returned, or echoed as ``error_message``.
    """

    class _ExplodingFactory:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(
            self, scope: Mapping[str, Any], safety: Mapping[str, Any]
        ) -> HttpTransport:
            self.calls += 1
            raise RuntimeError("simulated factory failure with target=https://leak")

    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _RecordingResultTransport()
    factory = _ExplodingFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.delivered
    assert result.started_delivery is not None and result.started_delivery.delivered
    assert result.finished_delivery is not None and result.finished_delivery.delivered
    started, finished = _split_posts(transport.posts)
    assert len(started) == 1 and len(finished) == 1
    body = finished[0]["body"]
    assert body["succeeded"] is False
    assert body["outcome"] == ExecutionOutcome.failed_safely.value
    assert body["error_code"] == "worker_runtime_failed"
    # The raw exception message never reaches the finished body.
    assert body["error_message"] is None
    assert "leak" not in str(body)
    # No retry: at-most-once.
    assert factory.calls == 1


async def test_failed_safely_finished_delivery_failure_reports_delivery_failed() -> (
    None
):
    """If the recovery ``failed_safely`` POST itself fails, the consumer
    reports ``finished_delivery_failed`` — no retry, no rerun."""

    class _ExplodingFactory:
        def __call__(
            self, scope: Mapping[str, Any], safety: Mapping[str, Any]
        ) -> HttpTransport:
            raise RuntimeError("simulated factory failure")

    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _RecordingResultTransport(finished_status=500)
    factory = _ExplodingFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.finished_delivery_failed
    assert result.started_delivery is not None and result.started_delivery.delivered
    assert result.finished_delivery is not None
    assert result.finished_delivery.delivered is False
    assert result.finished_delivery.status_code == 500
    # Exactly one finished attempt — no automatic retry.
    _, finished = _split_posts(transport.posts)
    assert len(finished) == 1
    # And the failed_safely body was still sent (so a manual consumer could
    # see what was attempted) — error_message is None.
    body = finished[0]["body"]
    assert body["outcome"] == ExecutionOutcome.failed_safely.value
    assert body["error_code"] == "worker_runtime_failed"
    assert body["error_message"] is None


# --- worker-finished delivery failure is reported, not retried -------------


async def test_finished_delivery_failure_is_reported_and_not_rerun() -> None:
    """Transport error during worker-finished → ``finished_delivery_failed``."""
    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _RecordingResultTransport(finished_status=500)
    factory = _RecordingTransportFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.finished_delivery_failed
    assert result.started_delivery is not None and result.started_delivery.delivered
    assert result.finished_delivery is not None
    assert result.finished_delivery.delivered is False
    assert result.finished_delivery.status_code == 500
    # No re-run: scanner transport was built exactly once.
    assert factory.calls == 1
    # And no automatic retry of worker-finished.
    _, finished = _split_posts(transport.posts)
    assert len(finished) == 1


async def test_finished_delivery_transport_error_is_reported_and_not_retried() -> None:
    """A raised exception from the transport on worker-finished is still safe."""

    class _FinishedOnlyExploding:
        def __init__(self) -> None:
            self.started_posts: list[str] = []

        async def post(
            self,
            url: str,
            *,
            json_body: dict[str, Any],
            headers: Mapping[str, str],
        ) -> WorkerDeliveryResponse:
            if url.endswith("/worker-started"):
                self.started_posts.append(url)
                return WorkerDeliveryResponse(status_code=200)
            raise RuntimeError("simulated worker-finished transport failure")

    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _FinishedOnlyExploding()
    factory = _RecordingTransportFactory()

    result = await consume_once(queue, _client(transport), transport_factory=factory)

    assert result.outcome is ConsumerOutcome.finished_delivery_failed
    assert result.started_delivery is not None and result.started_delivery.delivered
    # ``WorkerClient.deliver`` swallowed the transport error and reported it.
    assert result.finished_delivery is not None
    assert result.finished_delivery.delivered is False
    assert result.finished_delivery.failure == "transport_error"
    # Started was posted exactly once and the queue is empty (at-most-once).
    assert len(transport.started_posts) == 1
    assert factory.calls == 1
    assert queue.size() == 0


# --- kill switch active still posts started and finished -------------------


class _ActiveKillSwitch:
    """Kill switch that reports active on every poll."""

    async def is_active(self) -> bool:
        return True


async def test_active_kill_switch_still_posts_started_then_blocked_finished() -> None:
    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()
    kill_switch: KillSwitch = _ActiveKillSwitch()

    result = await consume_once(
        queue, _client(transport), kill_switch=kill_switch, transport_factory=factory
    )

    # The runner still produces a sanitized WorkerFinishedRequest with
    # blocked_by_control, so worker-finished IS posted.
    assert result.outcome is ConsumerOutcome.delivered
    assert result.started_delivery is not None and result.started_delivery.delivered
    assert result.finished_delivery is not None and result.finished_delivery.delivered

    started, finished = _split_posts(transport.posts)
    assert len(started) == 1
    assert len(finished) == 1
    # The finished body reports blocked_by_control, not validated/not_reproduced.
    assert finished[0]["body"]["outcome"] == ExecutionOutcome.blocked_by_control.value


# --- consume_available: bounded, FIFO --------------------------------------


async def test_consume_available_respects_max_messages() -> None:
    queue = InMemoryDispatchQueue()
    for i in range(5):
        queue.enqueue(_payload(execution_id=f"{i:08d}-0000-0000-0000-000000000000"))
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    results = await consume_available(
        queue, _client(transport), max_messages=3, transport_factory=factory
    )

    assert len(results) == 3
    assert all(r.outcome is ConsumerOutcome.delivered for r in results)
    # Two messages remain — the consumer never drains beyond the cap.
    assert queue.size() == 2


async def test_consume_available_stops_when_queue_empty_before_cap() -> None:
    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    results = await consume_available(
        queue, _client(transport), max_messages=10, transport_factory=factory
    )

    assert len(results) == 1
    assert queue.size() == 0
    # Exactly one scanner build, exactly one started + finished POST.
    assert factory.calls == 1
    started, finished = _split_posts(transport.posts)
    assert len(started) == 1 and len(finished) == 1


async def test_consume_available_preserves_fifo_order() -> None:
    queue = InMemoryDispatchQueue()
    ids = [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    ]
    for execution_id in ids:
        queue.enqueue(_payload(execution_id=execution_id))
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    await consume_available(
        queue, _client(transport), max_messages=10, transport_factory=factory
    )

    finished_urls = [
        p["url"] for p in transport.posts if p["url"].endswith("/worker-finished")
    ]
    assert finished_urls == [
        f"{_BASE_URL}/api/v1/validation-executions/{execution_id}/worker-finished"
        for execution_id in ids
    ]


def test_consume_available_rejects_non_positive_max_messages() -> None:
    import asyncio

    queue = InMemoryDispatchQueue()
    with pytest.raises(ValueError, match="positive"):
        asyncio.run(
            consume_available(
                queue,
                _client(_RecordingResultTransport()),
                max_messages=0,
            )
        )


# --- Log hygiene: no payload/token/snapshot/evidence -----------------------


async def test_no_token_or_payload_content_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())  # contains _SENSITIVE_TOKEN in the spec.
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    with caplog.at_level(logging.INFO, logger="securescope"):
        await consume_once(queue, _client(transport), transport_factory=factory)

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_TOKEN not in log_text
    assert _TARGET not in log_text
    assert "execution_specification" not in log_text
    assert "scope_snapshot" not in log_text
    assert "safety_snapshot" not in log_text
    # Evidence (response headers) is never logged either.
    for header_value in _STRONG_HEADERS.values():
        assert header_value not in log_text


async def test_malformed_path_logs_no_message_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = InMemoryDispatchQueue()
    queue._items.append(
        QueuedDispatchMessage(
            message_id="bad-3",
            message={"sensitive": _SENSITIVE_TOKEN, "target": _TARGET},
        )
    )
    transport = _RecordingResultTransport()
    factory = _RecordingTransportFactory()

    with caplog.at_level(logging.WARNING, logger="securescope"):
        await consume_once(queue, _client(transport), transport_factory=factory)

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_TOKEN not in log_text
    assert _TARGET not in log_text


async def test_runner_failure_logs_no_raw_exception_and_no_leak_in_finished(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The runner exception's text never reaches logs *or* the finished body."""

    class _LeakyFactory:
        def __call__(
            self, scope: Mapping[str, Any], safety: Mapping[str, Any]
        ) -> HttpTransport:
            raise RuntimeError(
                "https://leaked-target.example?token=" + _SENSITIVE_TOKEN
            )

    queue = InMemoryDispatchQueue()
    queue.enqueue(_payload())
    transport = _RecordingResultTransport()

    with caplog.at_level(logging.WARNING, logger="securescope"):
        result = await consume_once(
            queue, _client(transport), transport_factory=_LeakyFactory()
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_TOKEN not in log_text
    assert "leaked-target.example" not in log_text

    # And the recovered failed_safely body carries no leak from the exception.
    _, finished = _split_posts(transport.posts)
    body_text = str(finished[0]["body"])
    assert _SENSITIVE_TOKEN not in body_text
    assert "leaked-target.example" not in body_text
    # The run still closes out cleanly so the row leaves ``executing``.
    assert result.outcome is ConsumerOutcome.delivered


# --- Import purity ---------------------------------------------------------


_FORBIDDEN_IMPORT_TOKENS = (
    "fastapi",
    "sqlalchemy",
    "repository",
    "service",
    "router",
    "dispatcher",
    "app.main",
    "app.platform.database",
    "app.platform.dependencies",
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


def test_in_memory_consumer_imports_no_forbidden_modules() -> None:
    for module_name in _imported_modules(in_memory_consumer_module):
        assert not any(token in module_name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"in_memory_consumer must not import: {module_name}"
        )


def test_api_path_does_not_import_in_memory_consumer() -> None:
    """Dispatcher, service, and router never reach for the consumer."""
    for module in (dispatcher_module, service_module, router_module):
        names = _imported_modules(module)
        for module_name in names:
            assert "in_memory_consumer" not in module_name, (
                f"{module.__name__} must not import in_memory_consumer; "
                f"found: {module_name}"
            )


def test_main_does_not_import_in_memory_consumer() -> None:
    """The consumer is never wired into app startup."""
    from app import main as main_module

    for module_name in _imported_modules(main_module):
        assert "in_memory_consumer" not in module_name, (
            f"app.main must not import in_memory_consumer; found: {module_name}"
        )


def test_consumer_is_not_referenced_by_app_state() -> None:
    """No setting flips the consumer on at runtime — it is dev-tool-only.

    Verified by reading ``app/main.py`` source: no ``consume_once`` /
    ``consume_available`` / ``in_memory_consumer`` reference appears
    anywhere in the lifespan or factory.
    """
    from app import main as main_module

    source = main_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "in_memory_consumer" not in text
    assert "consume_once" not in text
    assert "consume_available" not in text
