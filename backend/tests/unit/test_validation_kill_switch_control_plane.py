"""Unit tests for the production control-plane kill switch (worker-side poller).

Exercise the real httpx wiring via an injected ``httpx.MockTransport``:
``is_active`` returns the control plane's boolean on a clean 200, and **fails
safe (abort)** on a non-200, an unreadable/omitted body, or a transport error —
so a scan that cannot confirm it is still permitted stops. Also covers the
per-execution factory and token non-leakage.
"""

import ast
import logging

import httpx
import pytest
from app.modules.validation_executions.kill_switch_control_plane import (
    ControlPlaneKillSwitch,
    build_control_plane_kill_switch_factory,
)

_BASE_URL = "https://control-plane.internal"
_EXECUTION_ID = "11111111-1111-1111-1111-111111111111"
_TOKEN = "kill-switch-poll-token-never-log"
_EXPECTED_URL = f"{_BASE_URL}/api/v1/validation-executions/{_EXECUTION_ID}/kill-switch"


class _Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []


def _switch(handler: object, *, token: str = _TOKEN) -> ControlPlaneKillSwitch:
    return ControlPlaneKillSwitch(
        _BASE_URL,
        _EXECUTION_ID,
        token,
        transport=httpx.MockTransport(handler),
    )


async def test_active_true_when_control_plane_reports_active() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json={"active": True})

    assert await _switch(handler).is_active() is True
    sent = recorder.requests[0]
    assert sent.method == "GET"
    assert str(sent.url) == _EXPECTED_URL
    assert sent.headers["X-Kill-Switch-Token"] == _TOKEN


async def test_active_false_when_control_plane_reports_inactive() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active": False})

    assert await _switch(handler).is_active() is False


async def test_non_200_aborts_fail_safe() -> None:
    # A revoked/expired/absent poll token yields 401 → abort.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "x"}})

    assert await _switch(handler).is_active() is True


async def test_missing_active_field_aborts_fail_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    assert await _switch(handler).is_active() is True


async def test_non_boolean_active_aborts_fail_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active": "yes"})

    assert await _switch(handler).is_active() is True


async def test_unreadable_body_aborts_fail_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    assert await _switch(handler).is_active() is True


async def test_transport_error_aborts_fail_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated", request=request)

    assert await _switch(handler).is_active() is True


async def test_token_not_logged_on_abort(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated", request=request)

    with caplog.at_level(logging.DEBUG, logger="securescope"):
        await _switch(handler).is_active()

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _TOKEN not in log_text


# --- factory ----------------------------------------------------------------


async def test_factory_builds_per_execution_switch() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, json={"active": True})

    factory = build_control_plane_kill_switch_factory(
        _BASE_URL, transport=httpx.MockTransport(handler)
    )
    switch = factory(_EXECUTION_ID, _TOKEN)

    assert await switch.is_active() is True
    sent = recorder.requests[0]
    assert str(sent.url) == _EXPECTED_URL
    assert sent.headers["X-Kill-Switch-Token"] == _TOKEN


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


def test_kill_switch_module_import_purity() -> None:
    from app.modules.validation_executions import (
        kill_switch_control_plane as module,
    )

    for name in _imported_modules(module):
        assert not any(token in name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"{module.__name__} must not import {name}"
        )
