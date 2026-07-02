"""Unit tests for the local isolated-worker runner.

The runner is exercised with a fake transport and fake transport factory so no
network is touched. Tests pin orchestration: template gating, malformed-input
rejection before any network call, transport-policy derivation, snapshot
passthrough, and kill-switch handling.
"""

import ast
from dataclasses import FrozenInstanceError, replace

import pytest
from app.modules.validation_executions.enums import ExecutionOutcome
from app.modules.validation_executions.executor_transport import HttpResponse
from app.modules.validation_executions.schemas import WorkerFinishedRequest
from app.modules.validation_executions.templates import (
    HTTP_SECURITY_HEADER_VALIDATION,
)
from app.modules.validation_executions.worker_runner import (
    MalformedWorkerInput,
    SafeHttpTransport,
    WorkerInput,
    _derive_transport_policy,
    _parse_allowed_ports,
    build_safe_http_transport,
    run_http_security_header_validation,
)

_TARGET = "https://app.example.com/login"

_STRONG_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=()",
}


class _FakeTransport:
    def __init__(self, response: HttpResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        return self._response


class _FakeFactory:
    def __init__(self, transport: _FakeTransport) -> None:
        self._transport = transport
        self.calls: list[tuple[object, object]] = []

    def __call__(self, scope: object, safety: object) -> _FakeTransport:
        self.calls.append((scope, safety))
        return self._transport


class _ActiveKillSwitch:
    async def is_active(self) -> bool:
        return True


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


def _fakes(
    headers: dict[str, str] | None = None,
) -> tuple[_FakeTransport, _FakeFactory]:
    transport = _FakeTransport(
        HttpResponse(
            200, headers if headers is not None else _STRONG_HEADERS, _TARGET, 8.0
        )
    )
    return transport, _FakeFactory(transport)


# --- Happy path -----------------------------------------------------------


async def test_happy_path_returns_worker_finished_request() -> None:
    transport, factory = _fakes()

    result = await run_http_security_header_validation(
        _worker_input(), transport_factory=factory
    )

    assert isinstance(result, WorkerFinishedRequest)
    assert result.outcome is ExecutionOutcome.not_reproduced
    assert result.succeeded is True
    # The runner ran the executor through the injected transport.
    assert factory.calls and len(transport.calls) == 1
    assert transport.calls[0]["method"] == "HEAD"


async def test_missing_headers_validated_through_mapper() -> None:
    # Empty headers -> executor reports validated -> mapper carries it through.
    _, factory = _fakes(headers={})

    result = await run_http_security_header_validation(
        _worker_input(), transport_factory=factory
    )

    assert result.outcome is ExecutionOutcome.validated
    # Evidence (mapper output) reaches the terminal step, not duplicated here.
    assert result.steps[-1].evidence is not None
    assert "missing_headers" in result.steps[-1].evidence


async def test_timeout_and_size_cap_passed_through() -> None:
    transport, factory = _fakes()
    worker_input = _worker_input(
        safety_snapshot={
            "timeout_seconds": 2.5,
            "redirect_limit": 1,
            "max_requests": 2,
            "max_response_bytes": 1024,
        }
    )

    await run_http_security_header_validation(worker_input, transport_factory=factory)

    assert transport.calls[0]["timeout_seconds"] == 2.5
    assert transport.calls[0]["max_response_bytes"] == 1024


async def test_snapshots_passed_to_transport_factory() -> None:
    _, factory = _fakes()
    worker_input = _worker_input(
        scope_snapshot={
            "allowed_paths": None,
            "excluded_paths": None,
            "allowed_ports": [8443],
        }
    )

    await run_http_security_header_validation(worker_input, transport_factory=factory)

    scope, safety = factory.calls[0]
    assert scope == worker_input.scope_snapshot
    assert safety == worker_input.safety_snapshot


# --- Template gating ------------------------------------------------------


async def test_unsupported_template_fails_safely_without_network() -> None:
    transport, factory = _fakes()

    result = await run_http_security_header_validation(
        _worker_input(template_id="SOMETHING_ELSE"), transport_factory=factory
    )

    assert result.outcome is ExecutionOutcome.failed_safely
    assert result.error_code == "unsupported_template"
    # No transport built, no request issued.
    assert factory.calls == []
    assert transport.calls == []


async def test_only_security_header_template_supported() -> None:
    # Sanity: any other template id never reaches the executor/transport.
    transport, factory = _fakes()
    for template in ("PORT_SCAN", "SQLI", "BRUTE_FORCE", ""):
        result = await run_http_security_header_validation(
            _worker_input(template_id=template), transport_factory=factory
        )
        assert result.outcome is ExecutionOutcome.failed_safely
    assert factory.calls == []
    assert transport.calls == []


# --- Malformed input (no network) -----------------------------------------


async def test_malformed_missing_safety_fields_raises_without_network() -> None:
    transport, factory = _fakes()
    worker_input = _worker_input(safety_snapshot={"timeout_seconds": 5.0})

    with pytest.raises(MalformedWorkerInput):
        await run_http_security_header_validation(
            worker_input, transport_factory=factory
        )
    assert factory.calls == []
    assert transport.calls == []


async def test_malformed_missing_target_raises_without_network() -> None:
    transport, factory = _fakes()
    worker_input = _worker_input(
        execution_specification={"template_id": HTTP_SECURITY_HEADER_VALIDATION}
    )

    with pytest.raises(MalformedWorkerInput):
        await run_http_security_header_validation(
            worker_input, transport_factory=factory
        )
    assert factory.calls == []
    assert transport.calls == []


async def test_malformed_missing_execution_id_raises() -> None:
    _, factory = _fakes()

    with pytest.raises(MalformedWorkerInput):
        await run_http_security_header_validation(
            _worker_input(execution_id=""), transport_factory=factory
        )
    assert factory.calls == []


# --- Transport policy derivation ------------------------------------------


def test_allow_http_defaults_false() -> None:
    allow_http, ports = _derive_transport_policy({}, {})
    assert allow_http is False
    assert ports == frozenset()


def test_allow_http_true_only_when_explicit() -> None:
    assert _derive_transport_policy({"allow_http": True}, {})[0] is True
    assert _derive_transport_policy({"allow_http": False}, {})[0] is False
    # May also be carried on the safety snapshot.
    assert _derive_transport_policy({}, {"allow_http": True})[0] is True


def test_allowed_ports_passed_through_from_scope() -> None:
    _, ports = _derive_transport_policy({"allowed_ports": [8443, 8080]}, {})
    assert ports == frozenset({8443, 8080})


def test_allowed_ports_absent_yields_empty_set() -> None:
    assert _derive_transport_policy({"allowed_ports": None}, {})[1] == frozenset()
    assert _derive_transport_policy({}, {})[1] == frozenset()


def test_build_safe_http_transport_returns_safe_transport() -> None:
    transport = build_safe_http_transport({"allowed_ports": [8443]}, {})
    assert isinstance(transport, SafeHttpTransport)


# --- allowed_ports hardening ----------------------------------------------


@pytest.mark.parametrize(
    "raw_ports",
    [
        [8443, 8080],
        (8443,),
        {8443, 9000},
        frozenset({443}),
        [1, 65535],
    ],
)
def test_parse_allowed_ports_accepts_valid_integer_collections(
    raw_ports: object,
) -> None:
    parsed = _parse_allowed_ports(raw_ports)
    assert parsed == frozenset(int(p) for p in raw_ports)  # type: ignore[union-attr]


def test_parse_allowed_ports_none_is_empty() -> None:
    assert _parse_allowed_ports(None) == frozenset()


@pytest.mark.parametrize(
    "raw_ports",
    [
        "8443",  # bare string, not a collection
        8443,  # bare int, not a collection
        {"port": 8443},  # mapping, not a port collection
        ["8443"],  # numeric string element
        ["https"],  # non-numeric string element
        [8443.0],  # float element
        [443, -1],  # negative port
        [0],  # zero port
        [70000],  # above the valid range
        [True],  # boolean masquerading as a port
        [False],  # boolean masquerading as a port
        [443, None],  # None element
    ],
)
def test_parse_allowed_ports_rejects_invalid(raw_ports: object) -> None:
    with pytest.raises(MalformedWorkerInput):
        _parse_allowed_ports(raw_ports)


async def test_invalid_allowed_ports_raises_without_building_transport() -> None:
    transport, factory = _fakes()
    worker_input = _worker_input(
        scope_snapshot={
            "allowed_paths": None,
            "excluded_paths": None,
            "allowed_ports": ["8443"],  # numeric string is rejected
        }
    )

    with pytest.raises(MalformedWorkerInput):
        await run_http_security_header_validation(
            worker_input, transport_factory=factory
        )
    # Failed during validation: no transport built, no request issued.
    assert factory.calls == []
    assert transport.calls == []


async def test_valid_allowed_ports_accepted_and_runs() -> None:
    transport, factory = _fakes()
    worker_input = _worker_input(
        scope_snapshot={
            "allowed_paths": None,
            "excluded_paths": None,
            "allowed_ports": [8443, 8080],
        }
    )

    result = await run_http_security_header_validation(
        worker_input, transport_factory=factory
    )

    assert result.outcome is ExecutionOutcome.not_reproduced
    assert len(transport.calls) == 1


# --- Kill switch ----------------------------------------------------------


async def test_active_kill_switch_maps_to_blocked_by_control() -> None:
    transport, factory = _fakes()

    result = await run_http_security_header_validation(
        _worker_input(), kill_switch=_ActiveKillSwitch(), transport_factory=factory
    )

    assert result.outcome is ExecutionOutcome.blocked_by_control
    # The executor checks the kill switch before any request is issued.
    assert transport.calls == []


# --- Purity ---------------------------------------------------------------


def test_worker_input_is_immutable() -> None:
    worker_input = _worker_input()
    with pytest.raises(FrozenInstanceError):
        worker_input.template_id = "x"  # type: ignore[misc]


def test_replace_produces_independent_input() -> None:
    base = _worker_input()
    other = replace(base, execution_id="exec-2")
    assert base.execution_id == "exec-1"
    assert other.execution_id == "exec-2"


def test_runner_module_imports_no_persistence_dispatch_or_api() -> None:
    import app.modules.validation_executions.worker_runner as runner_module

    source = runner_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)

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
    for module_name in imported:
        assert not any(token in module_name for token in forbidden), (
            f"runner must not import {module_name}"
        )
