"""Worker-side delivery client for the ``worker-finished`` hook.

After an isolated worker runs a validation it must report the sanitized result
back to the control plane. This client POSTs a :class:`WorkerFinishedRequest` to
``/api/v1/validation-executions/{execution_id}/worker-finished`` over an injected
transport, so it is exercised in tests without any network.

It is *worker-side only*: it performs no persistence, holds no session, and
imports no service/dispatcher/FastAPI machinery. The request body is exactly the
serialized :class:`WorkerFinishedRequest` (already sanitized upstream); nothing
else is added. Logs carry only the execution id and a coarse delivery status —
never evidence, tokens, response bodies, or raw transport/target exceptions.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

from pydantic import SecretStr

from app.modules.validation_executions.schemas import WorkerFinishedRequest

_logger = logging.getLogger("securescope.worker.delivery")

# Header carrying the short-lived, single-scan worker credential. The credential
# is provisioned out-of-band per scan — never a long-lived secret embedded in the
# frozen payload (``.claude/rules/security-boundaries.md`` → worker credentials).
_WORKER_AUTH_HEADER = "X-Worker-Authorization"


class WorkerDeliveryError(Exception):
    """Base class for worker result-delivery failures."""


class WorkerAuthNotConfigured(WorkerDeliveryError):
    """Worker authentication is required to deliver, but no credential is set.

    Raised before any network call so the result is never posted
    unauthenticated. No default credential is invented (fail closed).
    """


@dataclass(frozen=True, slots=True)
class WorkerDeliveryResponse:
    """Minimal response metadata from the delivery transport. No body retained."""

    status_code: int


class WorkerResultTransport(Protocol):
    """Posts one JSON body to a URL and returns the status only.

    Implementations perform the actual network I/O and are injected so the client
    is unit-tested without it. They expose only the status code: the worker needs
    nothing from the response body to judge delivery.
    """

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: Mapping[str, str],
    ) -> WorkerDeliveryResponse: ...


@dataclass(frozen=True, slots=True)
class WorkerDeliveryResult:
    """Outcome of attempting to deliver a worker-finished result.

    ``failure`` is a coarse, non-sensitive category set only when ``delivered``
    is ``False`` — never a raw exception or any target/transport detail.
    """

    delivered: bool
    status_code: int | None = None
    failure: str | None = None


class WorkerClient:
    """Delivers a :class:`WorkerFinishedRequest` to the worker-finished endpoint.

    ``base_url`` is the control-plane root. ``auth_token`` is the short-lived
    worker credential; when ``require_auth`` is true (the safe default) it must be
    present or delivery fails closed with :class:`WorkerAuthNotConfigured`.
    """

    def __init__(
        self,
        base_url: str,
        transport: WorkerResultTransport,
        *,
        auth_token: SecretStr | None = None,
        require_auth: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._auth_token = auth_token
        self._require_auth = require_auth

    async def start(self, execution_id: str) -> WorkerDeliveryResult:
        """POST the ``worker-started`` signal once and report the outcome.

        The worker-started hook takes no payload — the path-bound execution id
        identifies the row and the worker is identified by its credential. This
        is the lifecycle hand-off ``queued``/``dispatching`` → ``executing``;
        without it the control plane refuses the later ``worker-finished``
        post. As with :meth:`deliver` the credential is resolved before any
        network call (fail closed), transport errors and non-2xx statuses are
        reported as safe :class:`WorkerDeliveryResult` values rather than
        raising, and there is *no retry* — the caller decides whether to
        re-trigger the scan.
        """
        if not execution_id:
            raise WorkerDeliveryError(
                "execution_id is required to signal worker-started"
            )
        # May raise WorkerAuthNotConfigured — intentionally outside the try
        # below so a missing credential fails closed instead of being swallowed.
        headers = self._headers()
        url = (
            f"{self._base_url}/api/v1/validation-executions/"
            f"{quote(execution_id, safe='')}/worker-started"
        )
        try:
            response = await self._transport.post(url, json_body={}, headers=headers)
        except Exception:
            # Never echo a raw transport/target exception into logs or the result.
            _logger.warning(
                "worker-started signal failed for execution %s", execution_id
            )
            return WorkerDeliveryResult(delivered=False, failure="transport_error")

        delivered = 200 <= response.status_code < 300
        _logger.info(
            "worker-started signal for execution %s: delivered=%s status=%s",
            execution_id,
            delivered,
            response.status_code,
        )
        if not delivered:
            return WorkerDeliveryResult(
                delivered=False,
                status_code=response.status_code,
                failure="rejected",
            )
        return WorkerDeliveryResult(delivered=True, status_code=response.status_code)

    async def deliver(
        self, execution_id: str, request: WorkerFinishedRequest
    ) -> WorkerDeliveryResult:
        """POST the serialized result once and report the delivery outcome.

        Authentication is resolved first: if required but missing this raises
        before any network call (fail closed). A transport error or a non-2xx
        status is reported as a safe :class:`WorkerDeliveryResult`, not raised,
        so the caller records non-delivery without re-running the scan and
        without surfacing transport/target internals.
        """
        if not execution_id:
            raise WorkerDeliveryError("execution_id is required to deliver a result")

        # May raise WorkerAuthNotConfigured — intentionally outside the try below
        # so a missing credential fails closed instead of being swallowed.
        headers = self._headers()
        # Percent-encode the id as a single path segment so it cannot alter the
        # URL structure (no stray slashes/queries), even though control-plane ids
        # are UUIDs in practice.
        url = (
            f"{self._base_url}/api/v1/validation-executions/"
            f"{quote(execution_id, safe='')}/worker-finished"
        )
        body = request.model_dump(mode="json")

        try:
            response = await self._transport.post(url, json_body=body, headers=headers)
        except Exception:
            # Never echo a raw transport/target exception into logs or the result.
            _logger.warning(
                "worker result delivery failed for execution %s", execution_id
            )
            return WorkerDeliveryResult(delivered=False, failure="transport_error")

        delivered = 200 <= response.status_code < 300
        _logger.info(
            "worker result delivery for execution %s: delivered=%s status=%s",
            execution_id,
            delivered,
            response.status_code,
        )
        if not delivered:
            return WorkerDeliveryResult(
                delivered=False,
                status_code=response.status_code,
                failure="rejected",
            )
        return WorkerDeliveryResult(delivered=True, status_code=response.status_code)

    def _headers(self) -> dict[str, str]:
        """Build delivery headers, attaching the worker credential when present.

        Fails closed when authentication is required but no credential is
        configured rather than delivering unauthenticated.
        """
        headers = {"Content-Type": "application/json"}
        if self._auth_token is not None:
            headers[_WORKER_AUTH_HEADER] = self._auth_token.get_secret_value()
            return headers
        if self._require_auth:
            raise WorkerAuthNotConfigured(
                "worker authentication is required but no credential is configured"
            )
        return headers
