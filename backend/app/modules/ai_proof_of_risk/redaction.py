"""Deterministic redaction for AI Proof-of-Risk evidence.

Removes or masks credential-bearing headers, tokens, private keys, raw
request/response bodies, broker/database URLs, and opaque secrets before any
evidence reaches an AI provider or non-sensitive storage path.

This module performs no I/O and holds no state — pure functions over plain
values. See ``.claude/rules/data-handling.md`` and
``docs/ai-proof-of-risk-digital-twin-design.md``.
"""

import re

from app.modules.ai_proof_of_risk.enums import RedactionCategory
from app.modules.ai_proof_of_risk.schemas import RedactionEntry, RedactionResult

_REDACTED = "[REDACTED]"

# ---------------------------------------------------------------------------
# Header-level redaction
# ---------------------------------------------------------------------------

# Headers that are dropped entirely (case-insensitive match on key).
_CREDENTIAL_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "www-authenticate",
        "proxy-authenticate",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-session-token",
        "x-csrf-token",
    }
)

_HEADER_CATEGORY_MAP: dict[str, RedactionCategory] = {
    "authorization": RedactionCategory.authorization_header,
    "proxy-authorization": RedactionCategory.authorization_header,
    "www-authenticate": RedactionCategory.authorization_header,
    "proxy-authenticate": RedactionCategory.authorization_header,
    "cookie": RedactionCategory.cookie_header,
    "set-cookie": RedactionCategory.set_cookie_header,
    "x-api-key": RedactionCategory.api_key,
    "api-key": RedactionCategory.api_key,
    "x-auth-token": RedactionCategory.bearer_token,
    "x-session-token": RedactionCategory.session_id,
    "x-csrf-token": RedactionCategory.session_id,
}

# ---------------------------------------------------------------------------
# Value-level patterns
# ---------------------------------------------------------------------------

# Bearer tokens: ``Bearer <token>``
_BEARER_RE = re.compile(r"(?i)\bbearer\s+\S+")

# JWT-like values: three dot-separated base64url segments.
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

# Private key blocks: PEM-encoded keys.
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN[A-Z \t]+PRIVATE KEY-----[\s\S]*?-----END[A-Z \t]+PRIVATE KEY-----",
    re.DOTALL,
)

# Long opaque secrets (≥32 characters of base64/hex/url-safe chars).
_OPAQUE_SECRET_RE = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")

# Labelled secret assignments: ``token=<val>``, ``secret: <val>``, etc.
_LABELLED_SECRET_RE = re.compile(
    r"(?i)\b(bearer|token|secret|apikey|api[_-]?key|session(?:id)?|sid|password|passwd)\b[\s:=]+\S+"
)

# Database-like DSNs: ``postgresql://...``, ``amqp://...``, ``redis://...``
_DSN_RE = re.compile(
    r"(?i)(postgresql|postgres|amqp|amqps|redis|rediss|mysql|mongodb)://\S+"
)

# Fields that carry raw bodies and must be dropped entirely.
_RAW_BODY_FIELDS: frozenset[str] = frozenset(
    {
        "raw_request_body",
        "raw_response_body",
        "request_body",
        "response_body",
    }
)

# Fields that carry credential material and must be dropped entirely.
_CREDENTIAL_FIELDS: frozenset[str] = frozenset(
    {
        "worker_credential_raw_token",
        "worker_credential_token",
        "worker_token",
        "broker_url",
        "celery_broker_url",
        "database_url",
        "database_dsn",
        "db_url",
        "kill_switch_token",
    }
)

_CREDENTIAL_FIELD_CATEGORY: dict[str, RedactionCategory] = {
    "worker_credential_raw_token": RedactionCategory.worker_credential_token,
    "worker_credential_token": RedactionCategory.worker_credential_token,
    "worker_token": RedactionCategory.worker_credential_token,
    "broker_url": RedactionCategory.broker_url,
    "celery_broker_url": RedactionCategory.broker_url,
    "database_url": RedactionCategory.database_url,
    "database_dsn": RedactionCategory.database_url,
    "db_url": RedactionCategory.database_url,
    "kill_switch_token": RedactionCategory.kill_switch_token,
}


def _redact_string_value(value: str) -> tuple[str, list[RedactionCategory]]:
    """Mask secret patterns inside a string value.

    Returns the cleaned string and a list of redaction categories matched.
    """
    categories: list[RedactionCategory] = []

    if _PRIVATE_KEY_RE.search(value):
        value = _PRIVATE_KEY_RE.sub(_REDACTED, value)
        categories.append(RedactionCategory.private_key)

    if _JWT_RE.search(value):
        value = _JWT_RE.sub(_REDACTED, value)
        categories.append(RedactionCategory.jwt_value)

    if _BEARER_RE.search(value):
        value = _BEARER_RE.sub(_REDACTED, value)
        categories.append(RedactionCategory.bearer_token)

    if _DSN_RE.search(value):
        value = _DSN_RE.sub(_REDACTED, value)
        categories.append(RedactionCategory.database_url)

    if _LABELLED_SECRET_RE.search(value):
        value = _LABELLED_SECRET_RE.sub(_REDACTED, value)
        categories.append(RedactionCategory.opaque_secret)

    if _OPAQUE_SECRET_RE.search(value):
        value = _OPAQUE_SECRET_RE.sub(_REDACTED, value)
        categories.append(RedactionCategory.opaque_secret)

    return value, categories


def redact_evidence(evidence: dict[str, object]) -> RedactionResult:
    """Deterministically redact sensitive material from raw evidence.

    The evidence dict is shallow-copied; nested dicts (e.g. ``headers``) are
    walked one level deep. Keys matching credential or raw-body field names are
    removed. Values matching token, JWT, private-key, or DSN patterns are
    masked. The function is pure and deterministic — same input always produces
    the same output.
    """
    sanitized: dict[str, object] = {}
    entries: list[RedactionEntry] = []
    removed: list[str] = []
    warnings: list[str] = []

    for key, value in evidence.items():
        # Drop raw body fields entirely.
        if key.lower() in _RAW_BODY_FIELDS:
            original_len = len(str(value)) if value is not None else 0
            category = (
                RedactionCategory.raw_request_body
                if "request" in key.lower()
                else RedactionCategory.raw_response_body
            )
            entries.append(
                RedactionEntry(
                    category=category,
                    field_path=key,
                    original_length=original_len,
                )
            )
            removed.append(key)
            continue

        # Drop credential fields entirely.
        if key.lower() in _CREDENTIAL_FIELDS:
            original_len = len(str(value)) if value is not None else 0
            category = _CREDENTIAL_FIELD_CATEGORY.get(
                key.lower(), RedactionCategory.opaque_secret
            )
            entries.append(
                RedactionEntry(
                    category=category,
                    field_path=key,
                    original_length=original_len,
                )
            )
            removed.append(key)
            continue

        # Process nested header dicts.
        if key.lower() == "headers" and isinstance(value, dict):
            sanitized_headers: dict[str, object] = {}
            for hdr_name, hdr_value in value.items():
                hdr_lower = hdr_name.lower()
                if hdr_lower in _CREDENTIAL_HEADERS:
                    original_len = len(str(hdr_value)) if hdr_value is not None else 0
                    category = _HEADER_CATEGORY_MAP.get(
                        hdr_lower, RedactionCategory.opaque_secret
                    )
                    entries.append(
                        RedactionEntry(
                            category=category,
                            field_path=f"headers.{hdr_name}",
                            original_length=original_len,
                        )
                    )
                    removed.append(f"headers.{hdr_name}")
                    continue

                # Redact values inside non-credential headers.
                if isinstance(hdr_value, str):
                    cleaned, cats = _redact_string_value(hdr_value)
                    for cat in cats:
                        entries.append(
                            RedactionEntry(
                                category=cat,
                                field_path=f"headers.{hdr_name}",
                                original_length=len(hdr_value),
                            )
                        )
                    sanitized_headers[hdr_name] = cleaned
                else:
                    sanitized_headers[hdr_name] = hdr_value
            sanitized[key] = sanitized_headers
            continue

        # Redact string values at the top level.
        if isinstance(value, str):
            cleaned, cats = _redact_string_value(value)
            for cat in cats:
                entries.append(
                    RedactionEntry(
                        category=cat,
                        field_path=key,
                        original_length=len(value),
                    )
                )
            sanitized[key] = cleaned
        else:
            sanitized[key] = value

    if not removed and not entries:
        # Nothing was redacted — note this for audit.
        warnings.append("No sensitive material detected; verify input is raw evidence.")

    return RedactionResult(
        sanitized_evidence=sanitized,
        redaction_summary=entries,
        removed_fields=removed,
        safety_warnings=warnings,
    )
