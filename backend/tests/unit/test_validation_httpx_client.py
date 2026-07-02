"""Local integration tests for HttpxTransportClient.

These exercise the real httpx wiring (redirect policy, header passthrough,
timeout mapping, body handling) without touching the network, by injecting an
``httpx.MockTransport``. TLS certificate verification and SNI/IP pinning cannot
be exercised with a mock transport — that gap is documented as a known
limitation rather than faked here.
"""

import httpx
import pytest
from app.modules.validation_executions.executor_transport import TransportTimeout
from app.modules.validation_executions.http_transport import (
    HttpxTransportClient,
    TransportClientResponse,
)

_CONNECT_URL = "https://93.184.216.34:443/login"
_HEADERS = {"Host": "app.example.com", "User-Agent": "SecureScope-Validator/1.0"}


class _Recorder:
    """Captures the requests a MockTransport handler receives."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []


def _client(handler: object) -> HttpxTransportClient:
    return HttpxTransportClient(transport=httpx.MockTransport(handler))


async def _fetch(
    client: HttpxTransportClient,
    *,
    method: str = "HEAD",
    timeout_seconds: float = 5.0,
    max_response_bytes: int = 65536,
) -> TransportClientResponse:
    return await client.fetch(
        method=method,
        connect_url=_CONNECT_URL,
        headers=_HEADERS,
        sni_hostname="app.example.com",
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
    )


async def test_redirects_are_not_followed() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(302, headers={"location": "https://elsewhere.example/"})

    response = await _fetch(_client(handler))

    # The 302 is returned verbatim; the client did not chase the Location.
    assert response.status_code == 302
    assert len(recorder.requests) == 1


async def test_method_and_headers_passed_without_cookies_or_auth() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200, headers={"X-Frame-Options": "DENY"})

    await _fetch(_client(handler), method="GET")

    sent = recorder.requests[0]
    assert sent.method == "GET"
    assert sent.headers["Host"] == "app.example.com"
    assert sent.headers["User-Agent"] == "SecureScope-Validator/1.0"
    assert "cookie" not in sent.headers
    assert "authorization" not in sent.headers


async def test_response_is_metadata_only_no_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Referrer-Policy": "no-referrer"})

    response = await _fetch(_client(handler))

    assert response.status_code == 200
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.elapsed_ms is not None
    assert not hasattr(response, "body")
    assert not hasattr(response, "content")


async def test_large_body_is_bounded_and_not_exposed() -> None:
    # A body far larger than the cap must not error and must not surface.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1_000_000)

    response = await _fetch(_client(handler), max_response_bytes=128)

    assert response.status_code == 200
    assert not hasattr(response, "body")


async def test_timeout_is_mapped_to_transport_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated read timeout", request=request)

    with pytest.raises(TransportTimeout):
        await _fetch(_client(handler))


async def test_head_request_reaches_handler() -> None:
    recorder = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.requests.append(request)
        return httpx.Response(200)

    await _fetch(_client(handler), method="HEAD")

    assert recorder.requests[0].method == "HEAD"
    # No request body is sent for a HEAD.
    assert recorder.requests[0].content == b""
