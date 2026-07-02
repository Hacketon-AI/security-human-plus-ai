"""Production-safe HTTP transport for the isolated worker context.

This satisfies the :class:`HttpTransport` protocol the executor drives. It is
*worker-only*: it performs outbound network I/O and must never be constructed or
called from the API process or a Celery worker that shares the API image's
secrets (``.claude/rules/security-boundaries.md`` → Scanner execution isolation).
It is intentionally not wired into any dispatcher/service yet.

All policy is fixed at construction time (allowed schemes/ports) so the
executor-facing ``request`` keeps the protocol's narrow signature. Every request:

- is restricted to read-only ``HEAD``/``GET`` with no body, no cookies, no auth,
  and a single fixed ``User-Agent``;
- never follows redirects (the executor re-checks each hop and calls again);
- is bounded by an explicit timeout and response-size cap, and never exposes a
  body;
- is sent only after the target host is resolved and **every** resolved address
  is confirmed public. The connection is then pinned to that validated IP while
  the original hostname is preserved for ``Host``/SNI, which closes the DNS
  rebinding window: httpx performs no second resolution.

The actual httpx mechanics live in :class:`HttpxTransportClient`, injected so the
safety logic here is unit-tested with a fake client and resolver (no network).
"""

import ipaddress
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.modules.validation_executions.executor_transport import (
    HttpResponse,
    TransportError,
    TransportTargetBlocked,
    TransportTimeout,
)

# A single, honest, fixed identifier. No caller-supplied headers are ever sent.
_USER_AGENT = "SecureScope-Validator/1.0 (+passive-security-header-check)"

_SUPPORTED_METHODS = frozenset({"HEAD", "GET"})
_DEFAULT_PORTS: dict[str, int] = {"https": 443, "http": 80}


class AddressResolutionError(Exception):
    """The host could not be resolved. Mapped to a blocked target (fail closed)."""


class UnsupportedHttpMethod(TransportError):
    """A method other than HEAD/GET was requested. The transport is read-only."""


class AddressResolver(Protocol):
    """Resolves a hostname to its IP addresses immediately before connecting.

    Returns every address the name maps to so the transport can reject the whole
    target if any single address is non-public. Raises
    :class:`AddressResolutionError` on failure rather than returning an empty
    list, so "no records" cannot be mistaken for "resolved to nothing safe".
    """

    async def resolve(self, host: str) -> Sequence[str]: ...


@dataclass(frozen=True, slots=True)
class TransportClientResponse:
    """Raw response metadata from the injected client. Never carries a body.

    There is no final-URL field: redirects are never followed, so the requested
    URL is the only URL, and the transport reports the original hostname URL.
    """

    status_code: int
    headers: Mapping[str, str]
    elapsed_ms: float | None = None


class TransportClient(Protocol):
    """Executes one pinned request and returns metadata only.

    Implementations must not follow redirects, must send exactly ``headers`` (no
    cookies/auth added), must bound reads to ``max_response_bytes``, and must
    raise :class:`TransportTimeout` on timeout.
    """

    async def fetch(
        self,
        *,
        method: str,
        connect_url: str,
        headers: Mapping[str, str],
        sni_hostname: str | None,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> TransportClientResponse: ...


class SafeHttpTransport:
    """Policy-enforcing HTTP transport satisfying :class:`HttpTransport`.

    Construct once per scan from the frozen scope/safety policy. ``allow_http``
    and ``allowed_ports`` are the only escalations and both default to the
    safest value (https-only, default port only).
    """

    def __init__(
        self,
        *,
        allow_http: bool = False,
        allowed_ports: frozenset[int] = frozenset(),
        resolver: AddressResolver | None = None,
        client: TransportClient | None = None,
    ) -> None:
        self._allow_http = allow_http
        self._allowed_ports = allowed_ports
        # Production defaults are constructed lazily so importing this module
        # never requires httpx (a worker-only dependency).
        self._resolver = resolver if resolver is not None else SystemAddressResolver()
        self._client = client if client is not None else HttpxTransportClient()

    async def request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        """Validate, pin, and issue one read-only request; return metadata only."""
        normalized_method = method.upper()
        if normalized_method not in _SUPPORTED_METHODS:
            raise UnsupportedHttpMethod(f"method not permitted: {method}")

        parts = urlsplit(url)
        if parts.username or parts.password:
            raise TransportTargetBlocked("url carries embedded credentials")

        scheme = parts.scheme.lower()
        if scheme not in _DEFAULT_PORTS:
            raise TransportTargetBlocked(f"unsupported scheme: {scheme or '(none)'}")
        if scheme == "http" and not self._allow_http:
            raise TransportTargetBlocked("http scheme is not permitted")

        host = (parts.hostname or "").lower()
        if not host:
            raise TransportTargetBlocked("url has no host")
        if host == "localhost" or host.endswith(".localhost"):
            raise TransportTargetBlocked("localhost is not a permitted target")

        port = parts.port if parts.port is not None else _DEFAULT_PORTS[scheme]
        if port not in self._permitted_ports(scheme):
            raise TransportTargetBlocked(f"port not permitted: {port}")

        connect_ip = await self._resolve_and_validate(host)

        # Pin to the validated IP; preserve the original host for Host/SNI so
        # cert verification still checks the hostname and no second DNS lookup
        # can swap in a private address (DNS rebinding defence).
        is_default_port = port == _DEFAULT_PORTS[scheme]
        # ``_host_netloc`` brackets IPv6 literals and omits the default port, so
        # the Host header is well-formed for hostnames and IPv4/IPv6 literals.
        host_header = _host_netloc(host, port, is_default_port)
        connect_url = _build_url(scheme, _netloc_for_ip(connect_ip, port), parts)
        requested_url = _build_url(
            scheme, _host_netloc(host, port, is_default_port), parts
        )
        sni_hostname = host if scheme == "https" and not _is_ip_literal(host) else None

        headers = {"Host": host_header, "User-Agent": _USER_AGENT}

        client_response = await self._client.fetch(
            method=normalized_method,
            connect_url=connect_url,
            headers=headers,
            sni_hostname=sni_hostname,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )

        return HttpResponse(
            status_code=client_response.status_code,
            headers=client_response.headers,
            # Report the original hostname URL, not the pinned IP URL, so
            # evidence reflects the target the executor reasoned about.
            requested_url=requested_url,
            elapsed_ms=client_response.elapsed_ms,
        )

    def _permitted_ports(self, scheme: str) -> frozenset[int]:
        """Permitted ports for this scheme: only the scheme's own default plus
        any explicitly allowed ports.

        The default is scheme-specific, so ``https://host:80`` and
        ``http://host:443`` are both rejected unless their port is listed in
        ``allowed_ports``. ``allow_http`` gates the http *scheme*; it never
        widens the port set on its own.
        """
        return frozenset({_DEFAULT_PORTS[scheme]} | self._allowed_ports)

    async def _resolve_and_validate(self, host: str) -> str:
        """Return a single public IP to connect to, or raise if any is unsafe.

        An IP literal is validated directly. A hostname is resolved and *all*
        returned addresses are validated; a single non-public address blocks the
        whole target, defeating split-horizon and partial-rebind tricks.
        """
        if _is_ip_literal(host):
            _ensure_public(host)
            return host

        try:
            addresses = await self._resolver.resolve(host)
        except AddressResolutionError as exc:
            raise TransportTargetBlocked("host could not be resolved") from exc

        if not addresses:
            raise TransportTargetBlocked("host resolved to no addresses")
        for address in addresses:
            _ensure_public(address)
        return addresses[0]


def _ensure_public(address: str) -> None:
    """Raise :class:`TransportTargetBlocked` unless ``address`` is a public IP."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise TransportTargetBlocked(f"not an IP address: {address}") from exc
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        raise TransportTargetBlocked("target resolves to a non-public address")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _netloc_for_ip(ip: str, port: int) -> str:
    bracketed = f"[{ip}]" if ":" in ip else ip
    return f"{bracketed}:{port}"


def _host_netloc(host: str, port: int, is_default_port: bool) -> str:
    """Netloc for the original host, bracketing IPv6 literals."""
    bracketed = f"[{host}]" if ":" in host else host
    return bracketed if is_default_port else f"{bracketed}:{port}"


def _build_url(scheme: str, netloc: str, parts: SplitResult) -> str:
    """Rebuild a URL with a new netloc, dropping the fragment (and userinfo)."""
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))


async def _read_capped(chunks: AsyncIterator[bytes], max_bytes: int) -> int:
    """Consume an async byte stream up to ``max_bytes`` and discard it.

    The body is never retained or returned — reading only drains enough to
    complete the protocol exchange, bounded so a hostile endpoint cannot stream
    unbounded data. Returns the count read, for diagnostics only.
    """
    total = 0
    async for chunk in chunks:
        total += len(chunk)
        if total >= max_bytes:
            break
    return total


class SystemAddressResolver:
    """Production resolver using the event loop's non-blocking ``getaddrinfo``."""

    async def resolve(self, host: str) -> Sequence[str]:
        import asyncio
        import socket

        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise AddressResolutionError(f"resolution failed for {host}") from exc
        # De-duplicate while preserving order; index 4 is the sockaddr tuple.
        seen: dict[str, None] = {}
        for info in infos:
            seen.setdefault(str(info[4][0]), None)
        return list(seen)


class HttpxTransportClient:
    """Thin httpx adapter: one pinned, redirect-free, body-capped request.

    httpx is imported lazily so this module is importable without it (httpx is a
    worker-only dependency, not part of the API runtime). A fresh client is used
    per request so no cookie state can persist across calls.
    """

    def __init__(self, *, transport: Any = None) -> None:
        # Optional httpx.AsyncBaseTransport used only by local integration tests
        # to exercise the real httpx wiring without network I/O. Typed ``Any``
        # because httpx is imported lazily (worker-only) and must not be
        # referenced at module import time; ``None`` selects httpx's real
        # transport in production.
        self._transport = transport

    async def fetch(
        self,
        *,
        method: str,
        connect_url: str,
        headers: Mapping[str, str],
        sni_hostname: str | None,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> TransportClientResponse:
        import time

        import httpx

        extensions = {"sni_hostname": sni_hostname} if sni_hostname else {}
        timeout = httpx.Timeout(timeout_seconds)
        start = time.monotonic()
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            verify=True,
            trust_env=False,
            transport=self._transport,
        ) as client:
            request = client.build_request(
                method, connect_url, headers=dict(headers), extensions=extensions
            )
            try:
                response = await client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise TransportTimeout("request timed out") from exc
            try:
                await _read_capped(response.aiter_bytes(), max_response_bytes)
            finally:
                await response.aclose()
        elapsed_ms = (time.monotonic() - start) * 1000.0
        return TransportClientResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            elapsed_ms=elapsed_ms,
        )
