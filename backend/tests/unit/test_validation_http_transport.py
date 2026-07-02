"""Unit tests for the worker-side SafeHttpTransport.

The transport is exercised with a fake resolver and fake client so no network or
DNS is touched. Tests pin each safety control: scheme/port/userinfo/method gates,
IP classification, DNS-rebinding pinning, header hygiene, and error mapping.
"""

import ast
import inspect

import pytest
from app.modules.validation_executions.executor_transport import (
    TransportTargetBlocked,
    TransportTimeout,
)
from app.modules.validation_executions.http_transport import (
    AddressResolutionError,
    SafeHttpTransport,
    TransportClientResponse,
    UnsupportedHttpMethod,
    _read_capped,
)

_PUBLIC_IPV4 = "93.184.216.34"


class _FakeResolver:
    def __init__(self, addresses: list[str] | Exception) -> None:
        self._addresses = addresses
        self.hosts: list[str] = []

    async def resolve(self, host: str) -> list[str]:
        self.hosts.append(host)
        if isinstance(self._addresses, Exception):
            raise self._addresses
        return list(self._addresses)


class _FakeClient:
    def __init__(
        self,
        response: TransportClientResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response or TransportClientResponse(
            status_code=200,
            headers={"X-Frame-Options": "DENY"},
            elapsed_ms=12.0,
        )
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def fetch(
        self,
        *,
        method: str,
        connect_url: str,
        headers: dict[str, str],
        sni_hostname: str | None,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> TransportClientResponse:
        self.calls.append(
            {
                "method": method,
                "connect_url": connect_url,
                "headers": headers,
                "sni_hostname": sni_hostname,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        if self._error is not None:
            raise self._error
        return self._response


def _transport(
    *,
    resolver: _FakeResolver | None = None,
    client: _FakeClient | None = None,
    allow_http: bool = False,
    allowed_ports: frozenset[int] = frozenset(),
) -> tuple[SafeHttpTransport, _FakeResolver, _FakeClient]:
    resolver = resolver or _FakeResolver([_PUBLIC_IPV4])
    client = client or _FakeClient()
    transport = SafeHttpTransport(
        allow_http=allow_http,
        allowed_ports=allowed_ports,
        resolver=resolver,
        client=client,
    )
    return transport, resolver, client


async def _request(
    transport: SafeHttpTransport,
    method: str = "HEAD",
    url: str = "https://app.example.com/login",
) -> object:
    return await transport.request(
        method, url, timeout_seconds=5.0, max_response_bytes=65536
    )


# --- Method / body --------------------------------------------------------


async def test_head_request_success() -> None:
    transport, _, client = _transport()

    response = await _request(transport, "HEAD")

    assert response.status_code == 200
    assert response.requested_url == "https://app.example.com/login"
    assert response.elapsed_ms == 12.0
    assert client.calls[0]["method"] == "HEAD"


async def test_get_request_success() -> None:
    transport, _, client = _transport()

    await _request(transport, "GET")

    assert client.calls[0]["method"] == "GET"


async def test_unsupported_method_rejected() -> None:
    transport, _, client = _transport()

    for method in ("POST", "PUT", "DELETE", "OPTIONS", "PATCH"):
        with pytest.raises(UnsupportedHttpMethod):
            await _request(transport, method)
    assert client.calls == []  # never reached the network


def test_request_signature_accepts_no_body() -> None:
    params = inspect.signature(SafeHttpTransport.request).parameters
    assert "body" not in params
    assert "data" not in params
    assert "content" not in params
    # The injected client likewise has no body parameter.
    client_params = inspect.signature(_FakeClient.fetch).parameters
    assert "body" not in client_params and "data" not in client_params


# --- Header hygiene -------------------------------------------------------


async def test_only_host_and_user_agent_headers_sent() -> None:
    transport, _, client = _transport()

    await _request(transport)

    headers = client.calls[0]["headers"]
    assert set(headers) == {"Host", "User-Agent"}
    assert headers["Host"] == "app.example.com"
    # No cookies or auth, ever.
    lowered = {k.lower() for k in headers}
    assert "cookie" not in lowered
    assert "authorization" not in lowered


async def test_timeout_passed_to_client() -> None:
    transport, _, client = _transport()

    await transport.request(
        "HEAD", "https://app.example.com/", timeout_seconds=2.5, max_response_bytes=100
    )

    assert client.calls[0]["timeout_seconds"] == 2.5
    assert client.calls[0]["max_response_bytes"] == 100


async def test_no_raw_body_on_response() -> None:
    transport, _, _ = _transport()

    response = await _request(transport)

    assert not hasattr(response, "body")
    assert not hasattr(response, "response_body")
    assert not hasattr(response, "content")


# --- Scheme / port --------------------------------------------------------


async def test_https_on_443_allowed() -> None:
    transport, _, client = _transport()

    await _request(transport, "HEAD", "https://app.example.com:443/login")

    assert len(client.calls) == 1
    assert client.calls[0]["sni_hostname"] == "app.example.com"


async def test_http_denied_by_default() -> None:
    transport, _, client = _transport()

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "http://app.example.com/")
    assert client.calls == []


async def test_http_allowed_only_with_explicit_flag() -> None:
    transport, _, client = _transport(allow_http=True)

    await _request(transport, "HEAD", "http://app.example.com/")

    assert len(client.calls) == 1
    # http target carries no SNI.
    assert client.calls[0]["sni_hostname"] is None
    assert client.calls[0]["headers"]["Host"] == "app.example.com"


async def test_non_standard_port_rejected_by_default() -> None:
    transport, _, client = _transport()

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "https://app.example.com:8443/")
    assert client.calls == []


async def test_non_standard_port_allowed_when_in_scope() -> None:
    transport, _, client = _transport(allowed_ports=frozenset({8443}))

    await _request(transport, "HEAD", "https://app.example.com:8443/")

    assert len(client.calls) == 1
    assert ":8443" in str(client.calls[0]["connect_url"])


async def test_https_on_80_rejected_without_explicit_allow() -> None:
    # The https default permits 443 only; port 80 needs explicit allowed_ports
    # even though it is the http default.
    transport, _, client = _transport(allow_http=True)

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "https://app.example.com:80/")
    assert client.calls == []


async def test_https_on_80_allowed_when_in_scope() -> None:
    transport, _, client = _transport(allowed_ports=frozenset({80}))

    await _request(transport, "HEAD", "https://app.example.com:80/")

    assert len(client.calls) == 1


async def test_http_on_443_rejected_without_explicit_allow() -> None:
    # The http default permits 80 only; port 443 needs explicit allowed_ports.
    transport, _, client = _transport(allow_http=True)

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "http://app.example.com:443/")
    assert client.calls == []


async def test_http_on_443_allowed_when_in_scope() -> None:
    transport, _, client = _transport(allow_http=True, allowed_ports=frozenset({443}))

    await _request(transport, "HEAD", "http://app.example.com:443/")

    assert len(client.calls) == 1


async def test_userinfo_url_rejected() -> None:
    transport, _, client = _transport()

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "https://user:pass@app.example.com/")
    assert client.calls == []


async def test_unsupported_scheme_rejected() -> None:
    transport, _, _ = _transport()

    for url in ("ftp://app.example.com/", "file:///etc/passwd", "gopher://x/"):
        with pytest.raises(TransportTargetBlocked):
            await _request(transport, "HEAD", url)


# --- Hostname / IP classification ----------------------------------------


async def test_localhost_name_rejected() -> None:
    transport, resolver, client = _transport()

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "https://localhost/")
    assert resolver.hosts == []  # rejected before resolution
    assert client.calls == []


@pytest.mark.parametrize(
    "literal",
    [
        "127.0.0.1",  # loopback v4
        "10.0.0.5",  # private v4
        "192.168.1.10",  # private v4
        "169.254.10.10",  # link-local v4
        "224.0.0.1",  # multicast v4
        "0.0.0.0",  # unspecified v4  # noqa: S104 - rejection fixture, not a bind
        "240.0.0.1",  # reserved v4
        "::1",  # loopback v6
        "fd00::1",  # private/ULA v6
        "fe80::1",  # link-local v6
        "ff02::1",  # multicast v6
        "::",  # unspecified v6
    ],
)
async def test_non_public_ip_literal_rejected(literal: str) -> None:
    transport, _, client = _transport()
    host = f"[{literal}]" if ":" in literal else literal

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", f"https://{host}/")
    assert client.calls == []


async def test_private_address_from_resolution_rejected() -> None:
    # The name looks innocent but resolves to a private address.
    resolver = _FakeResolver(["10.1.2.3"])
    transport, _, client = _transport(resolver=resolver)

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "https://intranet.example.com/")
    assert client.calls == []


async def test_any_private_address_in_set_blocks_target() -> None:
    # One public and one private record: the whole target is blocked
    # (split-horizon / partial-rebind defence).
    resolver = _FakeResolver([_PUBLIC_IPV4, "192.168.0.1"])
    transport, _, client = _transport(resolver=resolver)

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "https://app.example.com/")
    assert client.calls == []


async def test_public_resolution_pins_to_resolved_ip() -> None:
    resolver = _FakeResolver([_PUBLIC_IPV4])
    transport, _, client = _transport(resolver=resolver)

    await _request(transport, "HEAD", "https://app.example.com/login")

    call = client.calls[0]
    # Connection is pinned to the validated IP, not the hostname.
    assert _PUBLIC_IPV4 in str(call["connect_url"])
    assert "app.example.com" not in str(call["connect_url"])
    # Host and SNI preserve the original name for routing and cert checks.
    assert call["headers"]["Host"] == "app.example.com"
    assert call["sni_hostname"] == "app.example.com"


async def test_public_ipv6_literal_host_header_is_bracketed() -> None:
    # A public IPv6 literal target must produce a bracketed Host header and a
    # bracketed pinned connect URL; SNI is omitted for an IP literal.
    transport, _, client = _transport()

    await _request(transport, "HEAD", "https://[2001:4860:4860::8888]/")

    call = client.calls[0]
    assert call["headers"]["Host"] == "[2001:4860:4860::8888]"
    assert "[2001:4860:4860::8888]:443" in str(call["connect_url"])
    assert call["sni_hostname"] is None


async def test_public_ipv6_literal_non_default_port_host_header_bracketed() -> None:
    transport, _, client = _transport(allowed_ports=frozenset({8443}))

    await _request(transport, "HEAD", "https://[2001:4860:4860::8888]:8443/")

    assert client.calls[0]["headers"]["Host"] == "[2001:4860:4860::8888]:8443"


async def test_dns_failure_mapped_to_blocked() -> None:
    resolver = _FakeResolver(AddressResolutionError("nxdomain"))
    transport, _, client = _transport(resolver=resolver)

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "https://does-not-exist.example.com/")
    assert client.calls == []


async def test_empty_resolution_blocked() -> None:
    resolver = _FakeResolver([])
    transport, _, client = _transport(resolver=resolver)

    with pytest.raises(TransportTargetBlocked):
        await _request(transport, "HEAD", "https://app.example.com/")
    assert client.calls == []


# --- Fragments / redirect policy ------------------------------------------


async def test_fragment_stripped_before_request() -> None:
    transport, _, client = _transport()

    response = await _request(transport, "HEAD", "https://app.example.com/p#secret")

    assert "#" not in str(client.calls[0]["connect_url"])
    assert response.requested_url == "https://app.example.com/p"


# --- Error mapping --------------------------------------------------------


async def test_timeout_propagates_as_transport_timeout() -> None:
    client = _FakeClient(error=TransportTimeout("slow"))
    transport, _, _ = _transport(client=client)

    with pytest.raises(TransportTimeout):
        await _request(transport)


# --- Response-size cap helper ---------------------------------------------


async def test_read_capped_stops_at_cap() -> None:
    async def _chunks() -> object:
        for _ in range(100):
            yield b"x" * 50

    read = await _read_capped(_chunks(), max_bytes=120)
    assert 120 <= read < 5000  # stopped near the cap, did not drain everything


async def test_read_capped_handles_empty_body() -> None:
    async def _empty() -> object:
        return
        yield  # pragma: no cover

    assert await _read_capped(_empty(), max_bytes=100) == 0


# --- Purity ---------------------------------------------------------------


def test_transport_module_imports_no_persistence_or_dispatch() -> None:
    import app.modules.validation_executions.http_transport as transport_module

    source = transport_module.__file__
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
    )
    for module_name in imported:
        assert not any(token in module_name for token in forbidden), (
            f"transport must not import {module_name}"
        )
