"""Local integration tests for the production worker hook-delivery transport.

Exercise the real httpx wiring (redirect policy, JSON body, header passthrough,
status-only response, body non-retention) via an injected ``httpx.MockTransport``
— no network. Also prove the transport + ``build_worker_client_factory`` drop
straight into the real :class:`WorkerClient` and worker bootstrap, so a worker
process authenticates and delivers both lifecycle hooks end to end.

TLS verification cannot be exercised through a mock transport; that gap is a
known limitation (documented, not faked), matching ``test_validation_httpx_client``.
"""

import ast
import logging

import httpx
import pytest
from app.modules.validation_executions.broker_contracts import (
    BrokerConsumerOutcome,
)
from app.modules.validation_executions.celery_worker_bootstrap import (
    run_validation_envelope_with_handoff,
)
from app.modules.validation_executions.worker_client import WorkerClient
from app.modules.validation_executions.worker_result_transport import (
    HttpxWorkerResultTransport,
    build_worker_client_factory,
)
from pydantic import SecretStr
from tests.unit.test_validation_worker_bootstrap import (
    _envelope_dict,
    _InactiveKillSwitch,
    _scanner_factory,
)

_BASE_URL = "https://control-plane.internal"
_STARTED_URL = f"{_BASE_URL}/api/v1/validation-executions/exec-1/worker-started"
_TOKEN = "worker-result-transport-token-never-log"


class _Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []


def _transport(handler: object) -> HttpxWorkerResultTransport:
    return HttpxWorkerResultTransport(transport=httpx.MockTransport(handler))


# --- transport: POST mechanics ----------------------------------------------


async def test_post_sends_json_body_and_headers() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200)

    response = await _transport(handler).post(
        _STARTED_URL,
        json_body={"succeeded": True},
        headers={"X-Worker-Authorization": _TOKEN, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    sent = recorder.requests[0]
    assert sent.method == "POST"
    assert str(sent.url) == _STARTED_URL
    assert sent.headers["X-Worker-Authorization"] == _TOKEN
    # The body is exactly the JSON we handed in (httpx uses compact separators).
    assert sent.read() == b'{"succeeded":true}'


async def test_post_does_not_follow_redirects() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(302, headers={"location": "https://elsewhere.internal/"})

    response = await _transport(handler).post(
        _STARTED_URL, json_body={}, headers={"X-Worker-Authorization": _TOKEN}
    )

    # 302 returned verbatim; the Location was not chased.
    assert response.status_code == 302
    assert len(recorder.requests) == 1


async def test_post_returns_status_only_no_body_retained() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # A large body must neither error nor surface on the response object.
        return httpx.Response(204, content=b"x" * 1_000_000)

    response = await _transport(handler).post(
        _STARTED_URL, json_body={}, headers={"X-Worker-Authorization": _TOKEN}
    )

    assert response.status_code == 204
    assert not hasattr(response, "body")
    assert not hasattr(response, "content")


async def test_post_propagates_timeout_for_client_to_handle() -> None:
    # The transport does not swallow transport errors; WorkerClient maps them to
    # a safe delivery result. Here we assert the exception reaches the caller.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated", request=request)

    with pytest.raises(httpx.ConnectTimeout):
        await _transport(handler).post(
            _STARTED_URL, json_body={}, headers={"X-Worker-Authorization": _TOKEN}
        )


async def test_transport_does_not_log_token(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    with caplog.at_level(logging.DEBUG, logger="securescope"):
        await _transport(handler).post(
            _STARTED_URL,
            json_body={},
            headers={"X-Worker-Authorization": _TOKEN},
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _TOKEN not in log_text


# --- factory + WorkerClient integration -------------------------------------


async def test_factory_builds_authenticated_client() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200)

    factory = build_worker_client_factory(
        _BASE_URL, transport=httpx.MockTransport(handler)
    )
    client = factory(SecretStr(_TOKEN))
    assert isinstance(client, WorkerClient)

    result = await client.start("exec-1")

    assert result.delivered is True
    sent = recorder.requests[0]
    assert str(sent.url) == _STARTED_URL
    assert sent.headers["X-Worker-Authorization"] == _TOKEN


# --- end-to-end: transport drives both hooks through the bootstrap ----------


async def test_transport_delivers_full_lifecycle_via_bootstrap() -> None:
    """The production transport + factory run the whole started→finished flow.

    Drives the real worker bootstrap with a live scanner fake; the only real
    httpx wiring is the hook delivery, mocked at the socket boundary. Proves the
    transport is a drop-in for the worker consumer's ``client_factory``.
    """
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        status = 200 if request.url.path.endswith("/worker-started") else 204
        return httpx.Response(status)

    factory = build_worker_client_factory(
        _BASE_URL, transport=httpx.MockTransport(handler)
    )

    class _FixedTokenSource:
        async def resolve(self, *, execution_id: str):  # type: ignore[no-untyped-def]
            from app.modules.validation_executions.worker_credential_contracts import (
                WorkerCredentialResolution,
                WorkerCredentialResolutionOutcome,
            )

            return WorkerCredentialResolution(
                outcome=WorkerCredentialResolutionOutcome.found,
                raw_token=SecretStr(_TOKEN),
            )

    result = await run_validation_envelope_with_handoff(
        _envelope_dict(),
        source=_FixedTokenSource(),
        client_factory=factory,
        kill_switch=_InactiveKillSwitch(),
        transport_factory=_scanner_factory,
    )

    assert result.outcome is BrokerConsumerOutcome.delivered
    paths = [r.url.path for r in recorder.requests]
    assert paths[0].endswith("/worker-started")
    assert paths[-1].endswith("/worker-finished")
    # Every hook carried the per-execution credential.
    for request in recorder.requests:
        assert request.headers["X-Worker-Authorization"] == _TOKEN


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


def test_result_transport_import_purity() -> None:
    from app.modules.validation_executions import (
        worker_result_transport as transport_module,
    )

    for name in _imported_modules(transport_module):
        assert not any(token in name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"{transport_module.__name__} must not import {name}"
        )
