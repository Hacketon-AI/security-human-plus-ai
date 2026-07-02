"""Unit tests for the worker-side HTTP security-header executor.

The executor is exercised entirely through a deterministic fake transport and a
fake kill switch. No network, no database, no dispatcher. Each test pins one
safety control or one outcome path.
"""

from collections.abc import Mapping

from app.modules.validation_executions.enums import ExecutionOutcome, StepStatus
from app.modules.validation_executions.executor import (
    execute_http_security_header_validation,
)
from app.modules.validation_executions.executor_transport import (
    HttpResponse,
    TransportTargetBlocked,
    TransportTimeout,
)
from app.modules.validation_executions.templates import (
    HTTP_SECURITY_HEADER_VALIDATION,
)

_TARGET = "https://app.example.com/login"

_STRONG_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=()",
}


class _FakeTransport:
    """Returns scripted responses; records every request issued."""

    def __init__(self, responses: list[HttpResponse | Exception]) -> None:
        self._responses = list(responses)
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
        if not self._responses:
            raise AssertionError("transport called more times than scripted")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class _FakeKillSwitch:
    """Kill switch that flips active after ``trip_after`` polls."""

    def __init__(self, active: bool = False, trip_after: int | None = None) -> None:
        self._active = active
        self._trip_after = trip_after
        self.polls = 0

    async def is_active(self) -> bool:
        self.polls += 1
        if self._trip_after is not None and self.polls > self._trip_after:
            return True
        return self._active


def _spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "template_id": HTTP_SECURITY_HEADER_VALIDATION,
        "target": _TARGET,
    }
    spec.update(overrides)
    return spec


def _scope(**overrides: object) -> dict[str, object]:
    scope: dict[str, object] = {
        "target": _TARGET,
        "allowed_paths": None,
        "excluded_paths": None,
    }
    scope.update(overrides)
    return scope


def _safety(**overrides: object) -> dict[str, object]:
    safety: dict[str, object] = {
        "timeout_seconds": 5.0,
        "redirect_limit": 3,
        "max_requests": 5,
        "max_response_bytes": 65536,
    }
    safety.update(overrides)
    return safety


async def _run(
    transport: _FakeTransport,
    *,
    spec: Mapping[str, object] | None = None,
    scope: Mapping[str, object] | None = None,
    safety: Mapping[str, object] | None = None,
    kill_switch: _FakeKillSwitch | None = None,
) -> object:
    return await execute_http_security_header_validation(
        specification=spec or _spec(),
        scope_snapshot=scope or _scope(),
        safety_snapshot=safety or _safety(),
        transport=transport,
        kill_switch=kill_switch,
    )


# --- HEAD / GET method behaviour ------------------------------------------


async def test_head_success_inspects_headers() -> None:
    transport = _FakeTransport([HttpResponse(200, _STRONG_HEADERS, _TARGET, 42.0)])

    result = await _run(transport)

    assert transport.calls == [("HEAD", _TARGET)]
    assert result.outcome is ExecutionOutcome.not_reproduced
    assert result.evidence["missing_headers"] == []
    assert result.evidence["weak_headers"] == []
    assert result.evidence["timing_bucket"] == "fast"


async def test_get_fallback_only_after_head_405() -> None:
    transport = _FakeTransport(
        [
            HttpResponse(405, {}, _TARGET),
            HttpResponse(200, _STRONG_HEADERS, _TARGET),
        ]
    )

    result = await _run(transport)

    assert transport.calls == [("HEAD", _TARGET), ("GET", _TARGET)]
    assert result.evidence["method"] == "GET"
    assert result.outcome is ExecutionOutcome.not_reproduced


async def test_no_get_fallback_after_unrelated_head_failure() -> None:
    # A 500 is a valid final response whose headers are still inspected; the
    # executor must not retry with GET.
    transport = _FakeTransport([HttpResponse(500, {}, _TARGET)])

    result = await _run(transport)

    assert transport.calls == [("HEAD", _TARGET)]
    assert result.evidence["method"] == "HEAD"
    # No security headers present -> the weakness is confirmed.
    assert result.outcome is ExecutionOutcome.validated


# --- Bounds ----------------------------------------------------------------


async def test_request_cap_enforced() -> None:
    # A same-origin redirect loop; the request cap stops it before exhaustion.
    redirect = HttpResponse(302, {"Location": _TARGET}, _TARGET)
    transport = _FakeTransport([redirect] * 10)

    result = await _run(transport, safety=_safety(max_requests=2, redirect_limit=10))

    assert result.outcome is ExecutionOutcome.inconclusive
    assert result.evidence["request_count"] == 2
    assert len(transport.calls) == 2


async def test_redirect_cap_enforced() -> None:
    redirect = HttpResponse(302, {"Location": _TARGET}, _TARGET)
    transport = _FakeTransport([redirect] * 10)

    result = await _run(transport, safety=_safety(max_requests=10, redirect_limit=2))

    assert result.outcome is ExecutionOutcome.inconclusive
    assert result.evidence["redirect_count"] == 3  # the hop that exceeded the cap


async def test_cross_origin_redirect_blocked() -> None:
    transport = _FakeTransport(
        [HttpResponse(302, {"Location": "https://evil.example.net/"}, _TARGET)]
    )

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.blocked_by_control
    assert transport.calls == [("HEAD", _TARGET)]


async def test_scheme_downgrade_redirect_blocked() -> None:
    transport = _FakeTransport(
        [HttpResponse(301, {"Location": "http://app.example.com/login"}, _TARGET)]
    )

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.blocked_by_control


async def test_final_url_scope_escape_blocked() -> None:
    transport = _FakeTransport(
        [HttpResponse(302, {"Location": "https://app.example.com/admin"}, _TARGET)]
    )
    scope = _scope(allowed_paths=["/login"], excluded_paths=["/admin"])

    result = await _run(transport, scope=scope)

    assert result.outcome is ExecutionOutcome.blocked_by_control


async def test_same_origin_redirect_followed() -> None:
    transport = _FakeTransport(
        [
            HttpResponse(302, {"Location": "/login/step2"}, _TARGET),
            HttpResponse(200, _STRONG_HEADERS, "https://app.example.com/login/step2"),
        ]
    )

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.not_reproduced
    assert result.evidence["redirect_count"] == 1
    assert result.evidence["final_url"] == "https://app.example.com/login/step2"


# --- Failure modes ---------------------------------------------------------


async def test_timeout_returns_inconclusive() -> None:
    transport = _FakeTransport([TransportTimeout("slow")])

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.inconclusive


async def test_transport_exception_returns_failed_safely() -> None:
    transport = _FakeTransport([RuntimeError("boom")])

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.failed_safely
    assert result.error_code == "runtimeerror"
    # The raw exception message must never appear in the summary or evidence.
    assert "boom" not in result.summary
    assert "boom" not in str(result.evidence)


async def test_target_blocked_returns_blocked_by_control() -> None:
    transport = _FakeTransport([TransportTargetBlocked("private ip")])

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.blocked_by_control


# --- Kill switch -----------------------------------------------------------


async def test_kill_switch_before_request_blocks() -> None:
    transport = _FakeTransport([HttpResponse(200, _STRONG_HEADERS, _TARGET)])
    kill = _FakeKillSwitch(active=True)

    result = await _run(transport, kill_switch=kill)

    assert result.outcome is ExecutionOutcome.blocked_by_control
    assert transport.calls == []  # never issued a request


async def test_kill_switch_after_request_blocks() -> None:
    # Inactive on the pre-request poll, active before reporting.
    transport = _FakeTransport([HttpResponse(200, _STRONG_HEADERS, _TARGET)])
    kill = _FakeKillSwitch(trip_after=2)

    result = await _run(transport, kill_switch=kill)

    assert result.outcome is ExecutionOutcome.blocked_by_control
    assert transport.calls == [("HEAD", _TARGET)]  # request happened, report blocked


# --- Outcome semantics -----------------------------------------------------


async def test_missing_headers_are_validated() -> None:
    transport = _FakeTransport([HttpResponse(200, {}, _TARGET)])

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.validated
    assert "Strict-Transport-Security" in result.evidence["missing_headers"]
    assert "X-Frame-Options/CSP-frame-ancestors" in result.evidence["missing_headers"]


async def test_weak_hsts_is_validated() -> None:
    headers = dict(_STRONG_HEADERS)
    headers["Strict-Transport-Security"] = "max-age=0"
    transport = _FakeTransport([HttpResponse(200, headers, _TARGET)])

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.validated
    assert "Strict-Transport-Security" in result.evidence["weak_headers"]


async def test_strong_headers_not_reproduced() -> None:
    transport = _FakeTransport([HttpResponse(200, _STRONG_HEADERS, _TARGET)])

    result = await _run(transport)

    assert result.outcome is ExecutionOutcome.not_reproduced


async def test_csp_frame_ancestors_satisfies_frame_control() -> None:
    headers = dict(_STRONG_HEADERS)
    del headers["X-Frame-Options"]  # only CSP frame-ancestors remains
    transport = _FakeTransport([HttpResponse(200, headers, _TARGET)])

    result = await _run(transport)

    assert (
        "X-Frame-Options/CSP-frame-ancestors" not in result.evidence["missing_headers"]
    )
    assert result.outcome is ExecutionOutcome.not_reproduced


async def test_cache_control_checked_only_for_sensitive_path() -> None:
    # Without the sensitive flag, a missing Cache-Control is not a finding.
    transport = _FakeTransport([HttpResponse(200, _STRONG_HEADERS, _TARGET)])
    assert (await _run(transport)).outcome is ExecutionOutcome.not_reproduced

    # With the sensitive flag, the absent Cache-Control becomes a finding.
    transport = _FakeTransport([HttpResponse(200, _STRONG_HEADERS, _TARGET)])
    result = await _run(transport, spec=_spec(sensitive_path=True))
    assert result.outcome is ExecutionOutcome.validated
    assert "Cache-Control" in result.evidence["missing_headers"]


# --- Purity ----------------------------------------------------------------


async def test_unsupported_template_fails_safely() -> None:
    transport = _FakeTransport([])
    result = await _run(transport, spec=_spec(template_id="SOMETHING_ELSE"))

    assert result.outcome is ExecutionOutcome.failed_safely
    assert result.error_code == "unsupported_template"
    assert transport.calls == []


async def test_no_response_body_in_result() -> None:
    transport = _FakeTransport([HttpResponse(200, _STRONG_HEADERS, _TARGET)])

    result = await _run(transport)

    assert "body" not in result.evidence
    assert "response_body" not in result.evidence


async def test_step_results_recorded() -> None:
    transport = _FakeTransport([HttpResponse(200, {}, _TARGET)])

    result = await _run(transport)

    names = {step.step_name for step in result.steps}
    assert "head_request" in names
    assert "evaluate_security_headers" in names
    assert all(isinstance(step.status, StepStatus) for step in result.steps)


def test_executor_module_imports_no_persistence_or_dispatch() -> None:
    # The executor must not *import* persistence or dispatch layers. Inspect the
    # import graph via the AST rather than raw text, so prose in docstrings does
    # not produce false positives.
    import ast

    import app.modules.validation_executions.executor as executor_module

    source = executor_module.__file__
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
    )
    for module_name in imported:
        assert not any(token in module_name for token in forbidden), (
            f"executor must not import {module_name}"
        )
