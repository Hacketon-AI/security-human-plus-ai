"""Local isolated-worker runner for ``HTTP_SECURITY_HEADER_VALIDATION``.

This is the entry point a future isolated worker process calls once it has been
handed an immutable execution payload. It is *worker-side only*: it performs no
persistence, calls no API route, and touches no dispatcher — it orchestrates the
existing pure pieces (transport → executor → result mapping) and returns the
:class:`WorkerFinishedRequest` the worker would post back to the control plane.

It is intentionally not wired into the API process or dispatcher. The runner
builds a :class:`SafeHttpTransport` from the frozen snapshots, runs the read-only
executor under an injected kill switch, and maps the sanitized result through the
shared :func:`to_worker_finished_request` mapper — no result logic is duplicated
here. A malformed payload is rejected before any transport is built, so broken
input can never trigger a network call.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.modules.validation_executions.enums import ExecutionOutcome
from app.modules.validation_executions.executor import (
    ExecutorResult,
    KillSwitch,
    execute_http_security_header_validation,
)
from app.modules.validation_executions.executor_transport import HttpTransport
from app.modules.validation_executions.http_transport import SafeHttpTransport
from app.modules.validation_executions.result_mapping import (
    to_worker_finished_request,
)
from app.modules.validation_executions.schemas import WorkerFinishedRequest
from app.modules.validation_executions.templates import (
    HTTP_SECURITY_HEADER_VALIDATION,
)

# Safety-snapshot fields the executor reads unconditionally (``_resolve_limits``).
# Their absence is a malformed payload, caught before any network work.
_REQUIRED_SAFETY_FIELDS: tuple[str, ...] = (
    "timeout_seconds",
    "redirect_limit",
    "max_requests",
    "max_response_bytes",
)

# A factory producing the transport from the frozen snapshots. Injected in tests
# so the runner can be exercised without real network I/O.
TransportFactory = Callable[[Mapping[str, Any], Mapping[str, Any]], HttpTransport]


class WorkerRunnerError(Exception):
    """Base class for worker-runner failures raised before execution."""


class MalformedWorkerInput(WorkerRunnerError):
    """The worker input payload is missing required fields or is ill-typed."""


@dataclass(frozen=True, slots=True)
class WorkerInput:
    """Immutable payload an isolated worker receives for one execution.

    Mirrors what the control plane froze at queue time. The runner treats every
    field as untrusted and validates it before acting.
    """

    execution_id: str
    template_id: str
    execution_specification: Mapping[str, Any]
    scope_snapshot: Mapping[str, Any]
    safety_snapshot: Mapping[str, Any]


_MIN_PORT = 1
_MAX_PORT = 65535


def _parse_allowed_ports(raw_ports: object) -> frozenset[int]:
    """Validate and coerce the port allow-list into a ``frozenset[int]``.

    Structured snapshots carry ``allowed_ports`` as a list of integers
    (``engagements.schemas`` → ``list[int]``); this enforces exactly that shape.
    A missing value yields an empty set. Anything else — a non-collection, a
    string, a float, a boolean, or a port outside ``1..65535`` — is a malformed
    payload and is rejected rather than silently dropped, so a bad value can
    never widen or narrow the permitted ports unnoticed.
    """
    if raw_ports is None:
        return frozenset()
    if not isinstance(raw_ports, list | tuple | set | frozenset):
        raise MalformedWorkerInput("allowed_ports must be a list of integer ports")
    ports: set[int] = set()
    for entry in raw_ports:
        # ``bool`` is a subclass of ``int``; reject it explicitly so ``True``/
        # ``False`` cannot masquerade as ports 1/0.
        if isinstance(entry, bool) or not isinstance(entry, int):
            raise MalformedWorkerInput("allowed_ports entries must be integers")
        if entry < _MIN_PORT or entry > _MAX_PORT:
            raise MalformedWorkerInput(
                f"allowed_ports entries must be in {_MIN_PORT}..{_MAX_PORT}"
            )
        ports.add(entry)
    return frozenset(ports)


def _derive_transport_policy(
    scope_snapshot: Mapping[str, Any], safety_snapshot: Mapping[str, Any]
) -> tuple[bool, frozenset[int]]:
    """Derive ``(allow_http, allowed_ports)`` from the frozen snapshots.

    Both default to the safest value: https only, no extra ports. ``allow_http``
    is enabled only when a snapshot carries it explicitly truthy; missing
    ``allowed_ports`` yields an empty set — never a broad default. Invalid port
    values raise :class:`MalformedWorkerInput`.
    """
    allow_http = bool(
        scope_snapshot.get("allow_http") or safety_snapshot.get("allow_http")
    )
    allowed_ports = _parse_allowed_ports(scope_snapshot.get("allowed_ports"))
    return allow_http, allowed_ports


def build_safe_http_transport(
    scope_snapshot: Mapping[str, Any], safety_snapshot: Mapping[str, Any]
) -> HttpTransport:
    """Default transport factory: a :class:`SafeHttpTransport` from the snapshots.

    Timeout and response-size caps are not constructor arguments — they live in
    the safety snapshot and the executor passes them to ``transport.request`` per
    request, so they are enforced without being baked into the transport.
    """
    allow_http, allowed_ports = _derive_transport_policy(
        scope_snapshot, safety_snapshot
    )
    return SafeHttpTransport(allow_http=allow_http, allowed_ports=allowed_ports)


async def run_http_security_header_validation(
    worker_input: WorkerInput,
    *,
    kill_switch: KillSwitch | None = None,
    transport_factory: TransportFactory | None = None,
) -> WorkerFinishedRequest:
    """Run one validation and return the worker-finished request.

    Unsupported templates resolve to a safe ``failed_safely`` result with no
    network work. A malformed payload raises :class:`MalformedWorkerInput`
    before a transport is built. The supported path builds the transport, runs
    the executor under ``kill_switch``, and maps the sanitized result through the
    shared mapper.
    """
    if worker_input.template_id != HTTP_SECURITY_HEADER_VALIDATION:
        # Reuse the mapper so the safe result shape is never duplicated.
        return to_worker_finished_request(
            ExecutorResult(
                outcome=ExecutionOutcome.failed_safely,
                summary="unsupported validation template",
                error_code="unsupported_template",
            )
        )

    _validate_payload(worker_input)

    factory = (
        transport_factory
        if transport_factory is not None
        else build_safe_http_transport
    )
    transport = factory(worker_input.scope_snapshot, worker_input.safety_snapshot)

    result = await execute_http_security_header_validation(
        specification=worker_input.execution_specification,
        scope_snapshot=worker_input.scope_snapshot,
        safety_snapshot=worker_input.safety_snapshot,
        transport=transport,
        kill_switch=kill_switch,
    )
    return to_worker_finished_request(result)


def _validate_payload(worker_input: WorkerInput) -> None:
    """Reject malformed input before any transport is built or request is sent."""
    if not worker_input.execution_id:
        raise MalformedWorkerInput("execution_id is required")

    spec = worker_input.execution_specification
    if not isinstance(spec, Mapping):
        raise MalformedWorkerInput("execution_specification must be a mapping")
    if "target" not in spec or not spec.get("target"):
        raise MalformedWorkerInput("execution_specification is missing target")
    if "template_id" not in spec:
        raise MalformedWorkerInput("execution_specification is missing template_id")

    if not isinstance(worker_input.scope_snapshot, Mapping):
        raise MalformedWorkerInput("scope_snapshot must be a mapping")

    safety = worker_input.safety_snapshot
    if not isinstance(safety, Mapping):
        raise MalformedWorkerInput("safety_snapshot must be a mapping")
    missing = [field for field in _REQUIRED_SAFETY_FIELDS if field not in safety]
    if missing:
        raise MalformedWorkerInput(
            f"safety_snapshot is missing fields: {', '.join(missing)}"
        )

    # Validate the transport port allow-list here so a malformed value fails
    # before any transport is built — independent of the injected factory.
    _parse_allowed_ports(worker_input.scope_snapshot.get("allowed_ports"))
