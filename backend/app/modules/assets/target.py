"""Target normalization per asset type.

Each asset type has a canonical target form. Normalization rejects malformed or
unsafe inputs (e.g. plaintext HTTP, embedded credentials, host bits set on a
CIDR) rather than silently rewriting them, so the stored target is both valid
and faithful to what the caller registered. IP and CIDR parsing uses the
standard library ``ipaddress`` module, never a hand-rolled regex.
"""

import re
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit, urlunsplit

from app.modules.assets.enums import AssetType
from app.modules.assets.errors import InvalidAssetTarget

# A conservative host:port shape for opaque service endpoints, and a permissive
# but space-free token for mobile application identifiers.
_SERVICE_ENDPOINT = re.compile(r"^[a-z0-9.-]+(?::(?P<port>\d{1,5}))?$")
_APP_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,199}$")

# Asset types whose canonical target is an HTTPS URL.
_HTTPS_URL_TYPES = frozenset(
    {AssetType.web_application, AssetType.api, AssetType.repository}
)


def normalize_target(asset_type: AssetType, raw: str) -> str:
    """Return the canonical target for ``asset_type`` or raise InvalidAssetTarget."""
    value = raw.strip()
    if not value:
        raise InvalidAssetTarget("target must not be empty")

    if asset_type in _HTTPS_URL_TYPES:
        return _normalize_https_url(value)
    if asset_type is AssetType.ip_address:
        return _normalize_ip(value)
    if asset_type is AssetType.cidr_range:
        return _normalize_cidr(value)
    if asset_type is AssetType.mobile_application:
        return _normalize_app_identifier(value)
    if asset_type is AssetType.service:
        return _normalize_service_endpoint(value)
    # Exhaustive over AssetType; a new member must extend this dispatch.
    raise InvalidAssetTarget(f"unsupported asset type for target: {asset_type.value}")


def hostname_from_target(target: str) -> str:
    """Return the lowercase hostname of an HTTPS asset target.

    Used to derive DNS verification record names from the already-normalized
    target, so the hostname is never taken from client input. Raises when the
    target carries no host (which should not happen for normalized web/api
    targets).
    """
    host = urlsplit(target).hostname
    if not host:
        raise InvalidAssetTarget("asset target has no host to verify")
    return host.lower()


def _normalize_https_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https":
        raise InvalidAssetTarget("target must use https")
    if not parts.hostname:
        raise InvalidAssetTarget("target must include a host")
    if parts.username or parts.password:
        # Embedded credentials are sensitive and must never be stored.
        raise InvalidAssetTarget("target must not embed credentials")

    host = parts.hostname.lower()
    netloc = f"{host}:{parts.port}" if parts.port else host
    path = parts.path or ""
    # Drop the fragment; preserve any query the caller registered.
    return urlunsplit(("https", netloc, path, parts.query, ""))


def _normalize_ip(value: str) -> str:
    try:
        return str(ip_address(value))
    except ValueError as exc:
        raise InvalidAssetTarget(f"invalid IP address: {value!r}") from exc


def _normalize_cidr(value: str) -> str:
    try:
        # strict=True rejects a network whose host bits are set, forcing the
        # caller to register an explicit network rather than guessing intent.
        return str(ip_network(value, strict=True))
    except ValueError as exc:
        raise InvalidAssetTarget(
            f"invalid CIDR range (use the network address): {value!r}"
        ) from exc


def _normalize_app_identifier(value: str) -> str:
    candidate = value.strip()
    if not _APP_IDENTIFIER.fullmatch(candidate):
        raise InvalidAssetTarget(f"invalid mobile application identifier: {value!r}")
    return candidate


def _normalize_service_endpoint(value: str) -> str:
    candidate = value.strip().lower()
    match = _SERVICE_ENDPOINT.fullmatch(candidate)
    if match is None:
        raise InvalidAssetTarget(f"invalid service endpoint: {value!r}")
    port = match.group("port")
    if port is not None and not (1 <= int(port) <= 65535):
        raise InvalidAssetTarget(f"service port out of range: {port}")
    return candidate
