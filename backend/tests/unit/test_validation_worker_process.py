"""Unit tests for the local isolated-worker process and delivery client.

Both the target-scan transport and the result-delivery transport are faked, so
no network is touched. Tests pin: one scan + one delivery per run, malformed
payloads failing before any target request or delivery, safe results still being
delivered, delivery failures never re-running the scan, worker-auth fail-closed
behavior, isolation from persistence/API imports, and no secrets/evidence in
logs.
"""

import ast
import logging

import pytest
from app.modules.validation_executions.enums import ExecutionOutcome, StepStatus
from app.modules.validation_executions.executor_transport import HttpResponse
from app.modules.validation_executions.schemas import (
    WorkerFinishedRequest,
    WorkerStepResult,
)
from app.modules.validation_executions.templates import (
    HTTP_SECURITY_HEADER_VALIDATION,
)
from app.modules.validation_executions.worker_client import (
    WorkerAuthNotConfigured,
    WorkerClient,
    WorkerDeliveryResponse,
)
from app.modules.validation_executions.worker_process import (
    InactiveKillSwitch,
    RunOnceResult,
    run_once,
)
from app.modules.validation_executions.worker_runner import (
    MalformedWorkerInput,
    WorkerInput,
)
from pydantic import SecretStr

_TARGET = "https://app.example.com/login"
_BASE_URL = "https://control.example"
_FINISHED_URL = f"{_BASE_URL}/api/v1/validation-executions/exec-1/worker-finished"

_STRONG_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=()",
}


# --- Fakes ----------------------------------------------------------------


class _FakeTargetTransport:
    """Stands in for SafeHttpTransport: records calls, optionally raises."""

    def __init__(
        self, response: HttpResponse, *, raises: Exception | None = None
    ) -> None:
        self._response = response
        self._raises = raises
        self.calls: list[tuple[str, str]] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        self.calls.append((method, url))
        if self._raises is not None:
            raise self._raises
        return self._response


class _FakeTargetFactory:
    def __init__(self, transport: _FakeTargetTransport) -> None:
        self._transport = transport
        self.calls: list[tuple[object, object]] = []

    def __call__(self, scope: object, safety: object) -> _FakeTargetTransport:
        self.calls.append((scope, safety))
        return self._transport


class _FakeResultTransport:
    """Captures the worker-finished POST instead of sending it."""

    def __init__(
        self, *, status_code: int = 200, raises: Exception | None = None
    ) -> None:
        self._status_code = status_code
        self._raises = raises
        self.calls: list[dict[str, object]] = []

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, object],
        headers: dict[str, str],
    ) -> WorkerDeliveryResponse:
        self.calls.append({"url": url, "json_body": json_body, "headers": headers})
        if self._raises is not None:
            raise self._raises
        return WorkerDeliveryResponse(status_code=self._status_code)


class _ActiveKillSwitch:
    async def is_active(self) -> bool:
        return True


# --- Builders -------------------------------------------------------------


def _worker_input(**overrides: object) -> WorkerInput:
    base: dict[str, object] = {
        "execution_id": "exec-1",
        "template_id": HTTP_SECURITY_HEADER_VALIDATION,
        "execution_specification": {
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "target": _TARGET,
        },
        "scope_snapshot": {"allowed_paths": None, "excluded_paths": None},
        "safety_snapshot": {
            "timeout_seconds": 5.0,
            "redirect_limit": 3,
            "max_requests": 5,
            "max_response_bytes": 65536,
        },
    }
    base.update(overrides)
    return WorkerInput(**base)  # type: ignore[arg-type]


def _strong_target() -> tuple[_FakeTargetTransport, _FakeTargetFactory]:
    transport = _FakeTargetTransport(HttpResponse(200, _STRONG_HEADERS, _TARGET, 8.0))
    return transport, _FakeTargetFactory(transport)


def _client(transport: _FakeResultTransport, **kwargs: object) -> WorkerClient:
    params: dict[str, object] = {"auth_token": SecretStr("worker-token")}
    params.update(kwargs)
    return WorkerClient(_BASE_URL, transport, **params)  # type: ignore[arg-type]


def _finished() -> WorkerFinishedRequest:
    return WorkerFinishedRequest(succeeded=True, outcome=ExecutionOutcome.validated)


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


# --- run_once happy path --------------------------------------------------


async def test_run_once_runs_runner_and_posts_result() -> None:
    target, factory = _strong_target()
    result_transport = _FakeResultTransport()
    client = _client(result_transport)

    out = await run_once(_worker_input(), client, transport_factory=factory)

    assert isinstance(out, RunOnceResult)
    assert out.finished.outcome is ExecutionOutcome.not_reproduced
    # The runner actually ran via the injected target transport.
    assert factory.calls and len(target.calls) == 1
    # Exactly one delivery POST to the worker-finished URL with the serialized body.
    assert len(result_transport.calls) == 1
    call = result_transport.calls[0]
    assert call["url"] == _FINISHED_URL
    assert call["json_body"] == out.finished.model_dump(mode="json")
    assert out.delivery.delivered is True
    assert out.delivery.status_code == 200


# --- WorkerClient serialization + auth ------------------------------------


async def test_worker_client_serializes_request_body() -> None:
    result_transport = _FakeResultTransport()
    client = _client(result_transport)
    request = WorkerFinishedRequest(
        succeeded=True,
        outcome=ExecutionOutcome.validated,
        result_summary="ok",
        steps=[
            WorkerStepResult(
                step_name="check",
                status=StepStatus.passed,
                evidence={"missing_headers": "none"},
            )
        ],
    )

    delivery = await client.deliver("exec-1", request)

    assert delivery.delivered is True
    body = result_transport.calls[0]["json_body"]
    # Body is exactly the serialized request — enums as values, nothing added.
    assert body == request.model_dump(mode="json")
    assert body["outcome"] == "validated"  # type: ignore[index]
    assert result_transport.calls[0]["headers"]["Content-Type"] == "application/json"  # type: ignore[index]


async def test_worker_client_includes_auth_header_when_configured() -> None:
    result_transport = _FakeResultTransport()
    client = WorkerClient(
        _BASE_URL, result_transport, auth_token=SecretStr("secret-token")
    )

    await client.deliver("exec-1", _finished())

    headers = result_transport.calls[0]["headers"]
    assert headers["X-Worker-Authorization"] == "secret-token"  # type: ignore[index]


async def test_worker_client_url_encodes_execution_id() -> None:
    result_transport = _FakeResultTransport()
    client = _client(result_transport)

    await client.deliver("weird id/../x", _finished())

    url = result_transport.calls[0]["url"]
    assert url == (
        "https://control.example/api/v1/validation-executions/"
        "weird%20id%2F..%2Fx/worker-finished"
    )
    # The id is a single encoded segment: no stray space or path separators.
    assert " " not in url
    assert "/../" not in url


async def test_worker_client_does_not_send_tenant_header() -> None:
    result_transport = _FakeResultTransport()
    client = _client(result_transport)

    await client.deliver("exec-1", _finished())

    headers = result_transport.calls[0]["headers"]
    # Worker hooks are machine-authenticated: only the worker header, never the
    # tenant X-Organization-Id header.
    assert "X-Organization-Id" not in headers
    assert "X-Worker-Authorization" in headers


async def test_worker_client_fails_closed_when_auth_required_but_missing() -> None:
    result_transport = _FakeResultTransport()
    client = WorkerClient(
        _BASE_URL, result_transport, auth_token=None, require_auth=True
    )

    with pytest.raises(WorkerAuthNotConfigured):
        await client.deliver("exec-1", _finished())
    # Fail closed before any network call: nothing was posted.
    assert result_transport.calls == []


# --- Malformed payload ----------------------------------------------------


async def test_malformed_payload_does_not_run_target_or_post() -> None:
    target, factory = _strong_target()
    result_transport = _FakeResultTransport()
    client = _client(result_transport)
    # execution_specification without a target is malformed.
    bad = _worker_input(
        execution_specification={"template_id": HTTP_SECURITY_HEADER_VALIDATION}
    )

    with pytest.raises(MalformedWorkerInput):
        await run_once(bad, client, transport_factory=factory)

    assert factory.calls == []
    assert target.calls == []
    assert result_transport.calls == []


# --- Safe results are still delivered -------------------------------------


async def test_failed_safely_result_is_still_posted() -> None:
    # A target transport that raises maps to failed_safely in the executor.
    target = _FakeTargetTransport(
        HttpResponse(200, {}, _TARGET, 1.0), raises=RuntimeError("boom")
    )
    factory = _FakeTargetFactory(target)
    result_transport = _FakeResultTransport()
    client = _client(result_transport)

    out = await run_once(_worker_input(), client, transport_factory=factory)

    assert out.finished.outcome is ExecutionOutcome.failed_safely
    # The raw target exception message never leaks into the delivered result.
    assert out.finished.error_message is None
    assert len(result_transport.calls) == 1
    assert out.delivery.delivered is True


async def test_active_kill_switch_blocks_and_posts_result() -> None:
    target, factory = _strong_target()
    result_transport = _FakeResultTransport()
    client = _client(result_transport)

    out = await run_once(
        _worker_input(),
        client,
        kill_switch=_ActiveKillSwitch(),
        transport_factory=factory,
    )

    assert out.finished.outcome is ExecutionOutcome.blocked_by_control
    # No target request was issued, but the blocked result is still delivered.
    assert target.calls == []
    assert len(result_transport.calls) == 1
    assert out.delivery.delivered is True


# --- Delivery failure: report safely, never re-run, never retry -----------


async def test_delivery_rejection_does_not_rerun_scan() -> None:
    target, factory = _strong_target()
    result_transport = _FakeResultTransport(status_code=503)
    client = _client(result_transport)

    out = await run_once(_worker_input(), client, transport_factory=factory)

    # Scan ran exactly once; a rejected delivery is not a reason to re-run it.
    assert len(factory.calls) == 1 and len(target.calls) == 1
    # A single delivery attempt — no retry loop.
    assert len(result_transport.calls) == 1
    assert out.delivery.delivered is False
    assert out.delivery.status_code == 503
    assert out.delivery.failure == "rejected"


async def test_delivery_transport_error_is_reported_safely() -> None:
    target, factory = _strong_target()
    result_transport = _FakeResultTransport(raises=ConnectionError("dns boom"))
    client = _client(result_transport)

    out = await run_once(_worker_input(), client, transport_factory=factory)

    assert out.delivery.delivered is False
    assert out.delivery.failure == "transport_error"
    # The scan ran once and delivery was attempted once — no retry loop.
    assert len(target.calls) == 1
    assert len(result_transport.calls) == 1


# --- Logging hygiene ------------------------------------------------------


async def test_no_token_or_evidence_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result_transport = _FakeResultTransport()
    token = "super-secret-worker-token"
    evidence_marker = "evidence-marker-value"
    client = WorkerClient(_BASE_URL, result_transport, auth_token=SecretStr(token))
    request = WorkerFinishedRequest(
        succeeded=True,
        outcome=ExecutionOutcome.validated,
        steps=[
            WorkerStepResult(
                step_name="check",
                status=StepStatus.passed,
                evidence={"k": evidence_marker},
            )
        ],
    )

    with caplog.at_level(logging.DEBUG, logger="securescope.worker.delivery"):
        await client.deliver("exec-1", request)

    assert token not in caplog.text
    assert evidence_marker not in caplog.text
    # The evidence still travels in the POST body — logs are not the body.
    body = result_transport.calls[0]["json_body"]
    assert body["steps"][0]["evidence"]["k"] == evidence_marker  # type: ignore[index]


# --- Defaults -------------------------------------------------------------


async def test_inactive_kill_switch_never_aborts() -> None:
    assert await InactiveKillSwitch().is_active() is False


# --- Isolation ------------------------------------------------------------


def test_worker_modules_have_no_persistence_or_api_imports() -> None:
    import app.modules.validation_executions.worker_client as worker_client
    import app.modules.validation_executions.worker_process as worker_process

    forbidden = (
        "dispatcher",
        "repository",
        "service",
        "models",
        "database",
        "sqlalchemy",
        "fastapi",
        "session",
    )
    for module in (worker_client, worker_process):
        for name in _imported_modules(module):
            assert not any(token in name for token in forbidden), (
                f"{module.__name__} must not import {name}"
            )


def test_worker_process_not_imported_by_api_modules() -> None:
    import app.modules.validation_executions.dispatcher as dispatcher
    import app.modules.validation_executions.router as router
    import app.modules.validation_executions.service as service

    for module in (router, dispatcher, service):
        for name in _imported_modules(module):
            assert "worker_process" not in name
            assert "worker_client" not in name
