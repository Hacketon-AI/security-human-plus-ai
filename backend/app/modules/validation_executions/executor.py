"""Worker-side safe executor for ``HTTP_SECURITY_HEADER_VALIDATION``.

This is the read-only check a future isolated worker runs against an in-scope
origin. It is a *pure, transport-injected library*: it never opens a socket,
touches the database, or calls the dispatcher. The API process must never run
this inline (``docs/stack-decision.md``); it exists so the isolated worker has a
single, auditable, bounded implementation to call.

What it does, and only this:

- A read-only ``HEAD`` to the in-scope target, falling back to ``GET`` only when
  ``HEAD`` is unsupported (405/501).
- Inspects response *headers* for the presence and basic validity of the
  standard security headers. It never reads, stores, or returns a body.
- Stays same-origin: every redirect hop is re-checked against the scope and the
  original origin; a cross-origin or scheme-downgrade redirect is refused.

Every bound from the safety snapshot is enforced (timeout, redirect cap, request
cap, response-size cap), the kill switch is polled before each request and
before returning, and all evidence is sanitized before it leaves this module.
There is no exploitation, mutation, crawling, fuzzing, authentication, or
credential handling here, by construction (``.claude/rules/security-boundaries.md``).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

from app.modules.validation_executions.enums import ExecutionOutcome, StepStatus
from app.modules.validation_executions.executor_transport import (
    HttpResponse,
    HttpTransport,
    TransportTargetBlocked,
    TransportTimeout,
)
from app.modules.validation_executions.sanitization import (
    sanitize_response_headers,
    sanitize_url,
)
from app.modules.validation_executions.templates import (
    HTTP_SECURITY_HEADER_VALIDATION,
)

_REDIRECT_STATUSES: frozenset[int] = frozenset({301, 302, 303, 307, 308})
# ``HEAD`` is only retried as ``GET`` when the server signals the method itself
# is unsupported — never on an unrelated 4xx/5xx, which is a valid final response
# whose headers we still inspect.
_HEAD_UNSUPPORTED_STATUSES: frozenset[int] = frozenset({405, 501})

_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


class KillSwitch(Protocol):
    """Abort signal the executor polls between phases.

    The control plane can set the abort state without waiting for the worker
    (``.claude/rules/scan-authorization.md`` → Kill switch); the worker passes an
    implementation that reports the current state. ``is_active`` returning
    ``True`` means stop promptly.
    """

    async def is_active(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class ExecutorStepResult:
    """One sanitized step within the execution. ``detail`` carries no secrets."""

    step_name: str
    status: StepStatus
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutorResult:
    """The safe, sanitized result an isolated worker would report back.

    Contains no secret, no raw response body, and no unmasked URL. ``evidence``
    holds only the safe metadata enumerated in ``.claude/rules/data-handling.md``.
    """

    outcome: ExecutionOutcome
    summary: str
    steps: tuple[ExecutorStepResult, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class _HeaderEvaluation:
    """Outcome of inspecting response headers for the required controls."""

    missing: list[str]
    weak: list[str]
    present: list[str]


@dataclass(frozen=True, slots=True)
class _Origin:
    scheme: str
    host: str
    port: int


def _parse_origin(url: str) -> _Origin | None:
    """Return the (scheme, host, port) origin, or ``None`` if unsafe/unparseable.

    Rejects anything that is not http(s), carries embedded credentials, or lacks
    a host. Embedded credentials are refused outright — the executor performs no
    credential handling, even in a redirect target.
    """
    parts = urlsplit(url)
    if parts.scheme not in _DEFAULT_PORTS:
        return None
    if parts.username or parts.password:
        return None
    host = (parts.hostname or "").lower()
    if not host:
        return None
    port = parts.port if parts.port is not None else _DEFAULT_PORTS[parts.scheme]
    return _Origin(scheme=parts.scheme, host=host, port=port)


def _path_in_scope(
    url: str,
    allowed_paths: Sequence[str] | None,
    excluded_paths: Sequence[str] | None,
) -> bool:
    """Check a URL's path against the frozen scope allow/deny lists.

    A non-empty ``allowed_paths`` restricts to those path prefixes; an empty or
    absent list imposes no path-level restriction (the verified origin is itself
    the scope). Exclusions always win.
    """
    path = urlsplit(url).path or "/"
    if excluded_paths:
        if any(_path_matches(path, prefix) for prefix in excluded_paths):
            return False
    if allowed_paths:
        return any(_path_matches(path, prefix) for prefix in allowed_paths)
    return True


def _path_matches(path: str, prefix: str) -> bool:
    """Prefix match on path segments (``/admin`` matches ``/admin/users``)."""
    if path == prefix:
        return True
    return path.startswith(prefix.rstrip("/") + "/")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive single-header lookup over the raw response headers."""
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def _hsts_ok(value: str) -> bool:
    """``Strict-Transport-Security`` must carry a positive ``max-age``."""
    for directive in value.split(";"):
        directive = directive.strip().lower()
        if directive.startswith("max-age"):
            _, _, raw = directive.partition("=")
            try:
                return int(raw.strip()) > 0
            except ValueError:
                return False
    return False


def _frame_protection(headers: Mapping[str, str], csp: str | None) -> str:
    """Classify clickjacking protection from XFO or CSP ``frame-ancestors``.

    Returns ``"present"``, ``"weak"``, or ``"missing"``. Either a valid
    ``X-Frame-Options`` or a CSP ``frame-ancestors`` directive satisfies the
    control.
    """
    xfo = _header(headers, "x-frame-options")
    if csp is not None and "frame-ancestors" in csp.lower():
        return "present"
    if xfo is not None:
        token = xfo.strip().lower()
        if token in {"deny", "sameorigin"}:
            return "present"
        return "weak"
    return "missing"


def _evaluate_headers(
    headers: Mapping[str, str], *, check_cache_control: bool
) -> _HeaderEvaluation:
    """Inspect headers for presence and basic validity of the required controls.

    Evaluation runs on the *raw* headers (before redaction) so a weak value is
    detected accurately; only the surfaced evidence is later sanitized.
    """
    missing: list[str] = []
    weak: list[str] = []
    present: list[str] = []

    def classify(name: str, value: str | None, is_valid: bool) -> None:
        if value is None:
            missing.append(name)
        elif not is_valid:
            weak.append(name)
        else:
            present.append(name)

    hsts = _header(headers, "strict-transport-security")
    classify("Strict-Transport-Security", hsts, hsts is not None and _hsts_ok(hsts))

    csp = _header(headers, "content-security-policy")
    classify("Content-Security-Policy", csp, csp is not None and bool(csp.strip()))

    xcto = _header(headers, "x-content-type-options")
    classify(
        "X-Content-Type-Options",
        xcto,
        xcto is not None and xcto.strip().lower() == "nosniff",
    )

    frame = _frame_protection(headers, csp)
    if frame == "missing":
        missing.append("X-Frame-Options/CSP-frame-ancestors")
    elif frame == "weak":
        weak.append("X-Frame-Options/CSP-frame-ancestors")
    else:
        present.append("X-Frame-Options/CSP-frame-ancestors")

    referrer = _header(headers, "referrer-policy")
    classify(
        "Referrer-Policy", referrer, referrer is not None and bool(referrer.strip())
    )

    permissions = _header(headers, "permissions-policy")
    classify(
        "Permissions-Policy",
        permissions,
        permissions is not None and bool(permissions.strip()),
    )

    if check_cache_control:
        cache = _header(headers, "cache-control")
        directives = {"no-store", "no-cache", "private"}
        classify(
            "Cache-Control",
            cache,
            cache is not None and any(token in cache.lower() for token in directives),
        )

    return _HeaderEvaluation(missing=missing, weak=weak, present=present)


def _timing_bucket(elapsed_ms: float | None) -> str | None:
    """Coarsen a latency measurement into a non-identifying bucket."""
    if elapsed_ms is None:
        return None
    if elapsed_ms < 100:
        return "fast"
    if elapsed_ms < 1000:
        return "normal"
    return "slow"


async def _aborted(kill_switch: KillSwitch | None) -> bool:
    return kill_switch is not None and await kill_switch.is_active()


@dataclass(slots=True)
class _RequestLog:
    """Mutable per-run counters bounded by the safety snapshot."""

    request_count: int = 0
    redirect_count: int = 0


def _terminal(
    outcome: ExecutionOutcome,
    summary: str,
    steps: list[ExecutorStepResult],
    log: _RequestLog,
    *,
    error_code: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> ExecutorResult:
    """Build a result, always recording the request/redirect counts as evidence."""
    body: dict[str, Any] = {
        "request_count": log.request_count,
        "redirect_count": log.redirect_count,
    }
    if evidence:
        body.update(evidence)
    return ExecutorResult(
        outcome=outcome,
        summary=summary,
        steps=tuple(steps),
        evidence=body,
        error_code=error_code,
    )


async def execute_http_security_header_validation(
    *,
    specification: Mapping[str, Any],
    scope_snapshot: Mapping[str, Any],
    safety_snapshot: Mapping[str, Any],
    transport: HttpTransport,
    kill_switch: KillSwitch | None = None,
) -> ExecutorResult:
    """Run the read-only security-header check and return a sanitized result.

    Pure and transport-injected: all I/O goes through ``transport``; the kill
    switch is polled before each request and before returning. Every failure
    mode resolves to one of the five safe outcomes — never an exception escaping
    to the caller and never an unbounded action.
    """
    steps: list[ExecutorStepResult] = []
    log = _RequestLog()

    if specification.get("template_id") != HTTP_SECURITY_HEADER_VALIDATION:
        return _terminal(
            ExecutionOutcome.failed_safely,
            "executor invoked for an unsupported template",
            steps,
            log,
            error_code="unsupported_template",
        )

    # Kill switch wins before any work is done.
    if await _aborted(kill_switch):
        return _terminal(
            ExecutionOutcome.blocked_by_control,
            "aborted by kill switch before dispatch",
            steps,
            log,
        )

    target = str(specification.get("target", ""))
    origin = _parse_origin(target)
    if origin is None:
        return _terminal(
            ExecutionOutcome.failed_safely,
            "target is not a usable https origin",
            steps,
            log,
            error_code="invalid_target",
        )

    allowed_paths = scope_snapshot.get("allowed_paths")
    excluded_paths = scope_snapshot.get("excluded_paths")
    if not _path_in_scope(target, allowed_paths, excluded_paths):
        return _terminal(
            ExecutionOutcome.blocked_by_control,
            "target path is outside the authorized scope",
            steps,
            log,
        )

    limits = _resolve_limits(safety_snapshot)
    check_cache_control = bool(specification.get("sensitive_path", False))

    method = "HEAD"
    url = target
    get_fallback_used = False

    while True:
        if await _aborted(kill_switch):
            return _terminal(
                ExecutionOutcome.blocked_by_control,
                "aborted by kill switch mid-run",
                steps,
                log,
            )

        if log.request_count >= limits.max_requests:
            return _terminal(
                ExecutionOutcome.inconclusive,
                "request budget exhausted before a final response",
                steps,
                log,
            )

        try:
            response = await transport.request(
                method,
                url,
                timeout_seconds=limits.timeout_seconds,
                max_response_bytes=limits.max_response_bytes,
            )
        except TransportTimeout:
            steps.append(
                ExecutorStepResult(
                    _step_name(method), StepStatus.inconclusive, "timeout"
                )
            )
            return _terminal(
                ExecutionOutcome.inconclusive,
                "request timed out within the bounded window",
                steps,
                log,
            )
        except TransportTargetBlocked:
            steps.append(
                ExecutorStepResult(
                    _step_name(method), StepStatus.failed, "target blocked by transport"
                )
            )
            return _terminal(
                ExecutionOutcome.blocked_by_control,
                "transport refused the target as out of policy",
                steps,
                log,
            )
        except Exception as exc:  # any other failure must fail safely, not escape
            steps.append(
                ExecutorStepResult(
                    _step_name(method), StepStatus.failed, "transport error"
                )
            )
            return _terminal(
                ExecutionOutcome.failed_safely,
                "executor stopped after an unexpected transport error",
                steps,
                log,
                error_code=_error_code(exc),
            )

        log.request_count += 1

        if response.status_code in _REDIRECT_STATUSES:
            redirect = _follow_redirect(
                url, origin, response, allowed_paths, excluded_paths
            )
            if redirect.blocked_reason is not None:
                steps.append(
                    ExecutorStepResult(
                        "redirect", StepStatus.failed, redirect.blocked_reason
                    )
                )
                return _terminal(
                    ExecutionOutcome.blocked_by_control,
                    f"redirect blocked: {redirect.blocked_reason}",
                    steps,
                    log,
                )
            if redirect.next_url is None:
                # A redirect status with no usable Location: treat the response
                # as final and inspect whatever headers it carries.
                break
            log.redirect_count += 1
            if log.redirect_count > limits.redirect_limit:
                return _terminal(
                    ExecutionOutcome.inconclusive,
                    "redirect limit exceeded before a final response",
                    steps,
                    log,
                )
            steps.append(
                ExecutorStepResult(
                    "redirect", StepStatus.passed, "same-origin redirect"
                )
            )
            url = redirect.next_url
            method = "HEAD"
            continue

        if (
            method == "HEAD"
            and not get_fallback_used
            and response.status_code in _HEAD_UNSUPPORTED_STATUSES
        ):
            steps.append(
                ExecutorStepResult(
                    "head_request",
                    StepStatus.skipped,
                    f"HEAD unsupported ({response.status_code}); retrying with GET",
                )
            )
            method = "GET"
            get_fallback_used = True
            continue

        break

    steps.append(
        ExecutorStepResult(_step_name(method), StepStatus.passed, "response received")
    )

    if await _aborted(kill_switch):
        return _terminal(
            ExecutionOutcome.blocked_by_control,
            "aborted by kill switch before reporting",
            steps,
            log,
        )

    evaluation = _evaluate_headers(
        response.headers, check_cache_control=check_cache_control
    )
    steps.append(
        ExecutorStepResult(
            "evaluate_security_headers",
            StepStatus.passed,
            f"{len(evaluation.missing)} missing, {len(evaluation.weak)} weak",
        )
    )

    # The check validates the finding "security headers are missing/weak". A
    # confirmed weakness reproduces the finding (``validated``); a fully hardened
    # response does not (``not_reproduced``).
    weakness_present = bool(evaluation.missing or evaluation.weak)
    outcome = (
        ExecutionOutcome.validated
        if weakness_present
        else ExecutionOutcome.not_reproduced
    )

    evidence = _build_evidence(response, method, evaluation, url)
    summary = (
        f"{len(evaluation.missing)} missing and {len(evaluation.weak)} weak "
        f"security headers on {evidence['final_url']}"
    )
    return _terminal(outcome, summary, steps, log, evidence=evidence)


@dataclass(frozen=True, slots=True)
class _SafetyLimits:
    timeout_seconds: float
    redirect_limit: int
    max_requests: int
    max_response_bytes: int


def _resolve_limits(safety_snapshot: Mapping[str, Any]) -> _SafetyLimits:
    """Read the enforced bounds from the frozen safety snapshot."""
    return _SafetyLimits(
        timeout_seconds=float(safety_snapshot["timeout_seconds"]),
        redirect_limit=int(safety_snapshot["redirect_limit"]),
        max_requests=int(safety_snapshot["max_requests"]),
        max_response_bytes=int(safety_snapshot["max_response_bytes"]),
    )


@dataclass(frozen=True, slots=True)
class _RedirectDecision:
    next_url: str | None = None
    blocked_reason: str | None = None


def _follow_redirect(
    current_url: str,
    origin: _Origin,
    response: HttpResponse,
    allowed_paths: Sequence[str] | None,
    excluded_paths: Sequence[str] | None,
) -> _RedirectDecision:
    """Decide whether a redirect may be followed, enforcing the origin guard.

    A redirect is refused (not merely skipped) when it leaves the original
    origin, downgrades scheme, carries credentials, or lands outside scope — any
    of which is a scope escape that maps to ``blocked_by_control``.
    """
    location = _header(response.headers, "location")
    if not location:
        return _RedirectDecision(next_url=None)
    next_url = urljoin(current_url, location)
    next_origin = _parse_origin(next_url)
    if next_origin is None:
        return _RedirectDecision(blocked_reason="unsafe redirect target")
    if next_origin != origin:
        return _RedirectDecision(blocked_reason="cross-origin redirect")
    if not _path_in_scope(next_url, allowed_paths, excluded_paths):
        return _RedirectDecision(blocked_reason="redirect outside scope")
    return _RedirectDecision(next_url=next_url)


def _build_evidence(
    response: HttpResponse,
    method: str,
    evaluation: _HeaderEvaluation,
    final_url: str,
) -> dict[str, Any]:
    """Assemble sanitized evidence — safe metadata only, never a body."""
    evidence: dict[str, Any] = {
        "final_url": sanitize_url(final_url),
        "status_code": response.status_code,
        "method": method,
        "response_headers": sanitize_response_headers(response.headers),
        "missing_headers": evaluation.missing,
        "weak_headers": evaluation.weak,
    }
    bucket = _timing_bucket(response.elapsed_ms)
    if bucket is not None:
        evidence["timing_bucket"] = bucket
    return evidence


def _step_name(method: str) -> str:
    return "get_request" if method == "GET" else "head_request"


def _error_code(exc: Exception) -> str:
    """A stable, non-sensitive error code from the exception type only.

    The exception *message* is never surfaced — it may echo a URL or response
    detail. Only the class name (lowercased) is reported.
    """
    return type(exc).__name__.lower()
