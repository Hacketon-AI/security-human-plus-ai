"""The injected HTTP transport seam for the worker-side executor.

The executor is a pure library: it owns the *policy* (which method, which
redirects are safe, when to stop) but performs no network I/O itself. A future
isolated worker supplies an :class:`HttpTransport` that performs the actual
read-only request inside its sandbox. Keeping I/O behind this Protocol lets the
executor be unit-tested with a deterministic fake and keeps scanner traffic out
of the API process entirely (``docs/stack-decision.md``).

Transport responsibilities the executor relies on but does not implement:

- Do **not** follow redirects. The executor inspects ``Location`` and decides,
  so the origin/scope guard runs on every hop.
- Do **not** attach cookies, ``Authorization``, or any credential, and do not
  persist cookies between calls.
- Resolve the target and refuse private/internal/link-local addresses unless
  the scope explicitly allows them, raising :class:`TransportTargetBlocked`.
  The executor's post-redirect origin guard is the second line of defence; this
  is the first (see ``.claude/rules/security-boundaries.md`` → Targets).
- Enforce ``max_response_bytes`` while reading, so a hostile endpoint cannot
  stream an unbounded body. The executor never asks for or stores a body.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


class TransportError(Exception):
    """Base class for transport-layer failures surfaced to the executor."""


class TransportTimeout(TransportError):
    """The request exceeded its bounded timeout. The executor treats this as a
    transient, non-definitive result (``inconclusive``)."""


class TransportTargetBlocked(TransportError):
    """The transport refused the target as out-of-policy before sending.

    Raised when name resolution lands on a private/internal/link-local address
    not permitted by scope, or the host is otherwise disallowed. The executor
    maps this to ``blocked_by_control`` — a safety control stopped the request.
    """


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A read-only HTTP response as seen by the executor.

    Carries only response metadata. There is deliberately no body field: the
    security-header check never needs one, and omitting it makes it impossible
    for raw response content to reach evidence. ``requested_url`` is the exact
    URL the transport contacted (used to anchor relative ``Location`` headers).
    ``elapsed_ms`` is optional timing the executor buckets coarsely.
    """

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    requested_url: str = ""
    elapsed_ms: float | None = None


class HttpTransport(Protocol):
    """A read-only HTTP transport the executor drives one request at a time.

    Implementations must not follow redirects, attach credentials, persist
    cookies, or read more than ``max_response_bytes``. They raise
    :class:`TransportTimeout` on timeout and :class:`TransportTargetBlocked`
    when the resolved target is out of policy.
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse: ...
