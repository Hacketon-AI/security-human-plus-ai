"""Evidence sanitization for worker-side executor output.

Raw scanner I/O is sensitive until normalized (``.claude/rules/data-handling.md``).
This module is the boundary that turns observed HTTP metadata into safe evidence:
it drops credential-bearing headers, redacts token-like values, and strips
credentials and query strings from URLs before anything is returned by the
executor. It performs no I/O and holds no state — pure functions over plain
values so they can be unit-tested in isolation and reused by the worker-finished
service path.
"""

import re
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

# Header names that may carry credentials, tokens, or session material. These
# are never surfaced in evidence regardless of any allow-list, so an
# implementation change to the surfaced set can never leak them.
SENSITIVE_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "www-authenticate",
        "proxy-authenticate",
        "authentication-info",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-session-token",
        "x-csrf-token",
    }
)

# Response headers the security-header check legitimately surfaces. Anything
# outside this set is dropped: evidence carries only what the check evaluates,
# plus the content type, never arbitrary response headers.
SURFACED_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "strict-transport-security",
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
        "cache-control",
        "content-type",
    }
)

_REDACTED = "[REDACTED]"

# Opaque token shapes: a long base64/hex/url-safe run is treated as a secret and
# masked even inside an otherwise-safe header value (e.g. a CSP nonce/hash).
_OPAQUE_TOKEN = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")
# ``bearer <token>`` / ``token=<value>`` style assignments.
_LABELLED_SECRET = re.compile(
    r"(?i)\b(bearer|token|secret|apikey|api[_-]?key|session(?:id)?|sid)\b[\s:=]+\S+"
)

_MAX_HEADER_VALUE_CHARS = 300


def redact_header_value(value: str) -> str:
    """Mask token-like substrings in a header value and bound its length.

    Surfaced security headers rarely carry secrets, but CSP nonces/hashes and
    misconfigured values can. Masking here is defence-in-depth so evidence never
    persists an opaque credential even if one appears in a surfaced header.
    """
    redacted = _LABELLED_SECRET.sub(_REDACTED, value)
    redacted = _OPAQUE_TOKEN.sub(_REDACTED, redacted)
    if len(redacted) > _MAX_HEADER_VALUE_CHARS:
        redacted = redacted[:_MAX_HEADER_VALUE_CHARS] + "…"
    return redacted


def sanitize_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return only surfaced, redacted headers keyed by lowercase name.

    Sensitive headers are excluded unconditionally; surfaced headers pass
    through :func:`redact_header_value`. Header names are matched
    case-insensitively because transports may preserve arbitrary casing.
    """
    sanitized: dict[str, str] = {}
    for name, value in headers.items():
        lname = name.lower()
        if lname in SENSITIVE_HEADER_NAMES:
            continue
        if lname not in SURFACED_HEADER_NAMES:
            continue
        sanitized[lname] = redact_header_value(value)
    return sanitized


def sanitize_url(url: str) -> str:
    """Strip credentials, query, and fragment, leaving safe location metadata.

    Userinfo (``user:pass@``) and the query string can both carry credentials or
    session tokens, so only scheme, host, optional port, and path are kept. The
    host is lowercased for a stable representation.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    netloc = host
    if parts.port is not None:
        netloc = f"{host}:{parts.port}"
    # Drop userinfo, query, and fragment by reconstructing from cleaned parts.
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
