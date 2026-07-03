"""Production hook-delivery transport for the isolated worker.

The worker reports lifecycle to the control plane over two hooks —
``worker-started`` and ``worker-finished``. :class:`WorkerClient` builds the URL,
body, and auth header and delegates the actual network call to an injected
:class:`WorkerResultTransport`. This module is that transport for production: one
bounded, redirect-free JSON ``POST`` to the *first-party* control plane.

It is the counterpart to the scanner-side :class:`HttpxTransportClient` but for a
different direction of traffic: the scanner transport reaches untrusted scan
targets (and so pins IPs and blocks private ranges); this one reaches the known,
operator-configured control-plane base URL, so it does standard TLS-verified
delivery and does not follow redirects. Only the status code is read — no
response body is retained, so a hostile or oversized response cannot smuggle data
back into the worker.

Import purity: the worker client, its response type, and (lazily, inside the
call) ``httpx`` — a worker-only dependency never pulled into the API import
graph. No FastAPI, SQLAlchemy, repositories, services, routers, dispatcher, or
``app.main``.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import SecretStr

from app.modules.validation_executions.worker_client import (
    WorkerClient,
    WorkerDeliveryResponse,
)

__all__ = [
    "DEFAULT_WORKER_DELIVERY_TIMEOUT_SECONDS",
    "HttpxWorkerResultTransport",
    "build_worker_client_factory",
]

_logger = logging.getLogger("securescope.worker.result_transport")

# Deliveries to the control plane are small and local; a tight default timeout
# keeps a stalled hook from wedging a worker. The worker never retries a hook
# (re-running a scan is an operator decision), so this is a single bounded wait.
DEFAULT_WORKER_DELIVERY_TIMEOUT_SECONDS = 10.0


class HttpxWorkerResultTransport:
    """Deliver one worker hook via a bounded, redirect-free httpx ``POST``.

    Satisfies :class:`WorkerResultTransport`. ``timeout_seconds`` bounds the whole
    exchange. ``transport`` is an optional ``httpx.AsyncBaseTransport`` used by
    tests to drive the real httpx wiring without network I/O (an
    ``httpx.MockTransport``); ``None`` selects httpx's real transport in
    production. Typed ``Any`` because httpx is imported lazily and must not be
    referenced at module import time.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_WORKER_DELIVERY_TIMEOUT_SECONDS,
        transport: Any = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: Mapping[str, str],
    ) -> WorkerDeliveryResponse:
        """POST ``json_body`` to ``url`` and return the status only.

        The body is sent exactly as given (already the serialized, sanitized
        hook payload). Redirects are not followed — a redirect from the control
        plane is unexpected and surfaces as a non-2xx the client treats as
        undelivered. The response body is never read: the worker judges delivery
        from the status code alone, so nothing flows back into the process. The
        ``headers`` carry the short-lived worker credential; it is passed
        straight to httpx and never logged here.
        """
        import httpx

        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            verify=True,
            trust_env=False,
            transport=self._transport,
        ) as client:
            request = client.build_request(
                "POST", url, json=json_body, headers=dict(headers)
            )
            # Stream so the status/headers arrive without pulling the body; close
            # immediately — the body is never inspected.
            response = await client.send(request, stream=True)
            await response.aclose()
        return WorkerDeliveryResponse(status_code=response.status_code)


def build_worker_client_factory(
    base_url: str,
    *,
    timeout_seconds: float = DEFAULT_WORKER_DELIVERY_TIMEOUT_SECONDS,
    transport: Any = None,
) -> Callable[[SecretStr], WorkerClient]:
    """Build the per-execution :class:`WorkerClient` factory for a worker process.

    Returns a callable of the shape the worker bootstrap expects
    (``WorkerClientFactory`` in :mod:`celery_worker_bootstrap`): the bootstrap
    resolves the per-execution raw token from the side-channel and calls this to
    get an authenticated client bound to the control-plane ``base_url``. One
    :class:`HttpxWorkerResultTransport` is shared across calls — it holds no
    per-request state (a fresh httpx client is created per delivery). The raw
    token stays inside its :class:`SecretStr` until :class:`WorkerClient` reads it
    for the auth header; this builder never unwraps or logs it.
    """
    result_transport = HttpxWorkerResultTransport(
        timeout_seconds=timeout_seconds, transport=transport
    )

    def factory(raw_token: SecretStr) -> WorkerClient:
        return WorkerClient(base_url, result_transport, auth_token=raw_token)

    return factory
