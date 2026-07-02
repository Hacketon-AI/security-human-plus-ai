"""Token, digest, and DNS record helpers for ownership verification.

Pure functions kept apart from the service so they can be unit-tested without a
database. The raw token is high-entropy and returned to the caller exactly once;
only its digest is ever persisted. SHA-256 over the full record value is used
(no application secret is provisioned yet, and the token already carries 256-bit
entropy); migrating to HMAC-with-secret is future hardening.
"""

import hashlib
import hmac
import secrets

# 32 bytes => 256 bits of entropy, per the security requirement.
_TOKEN_BYTES = 32
_RECORD_NAME_PREFIX = "_securescope-verification"
_RECORD_VALUE_PREFIX = "securescope-verification="

# The DNS record type callers must publish.
RECORD_TYPE = "TXT"


def generate_token() -> str:
    """Return a fresh URL-safe token with at least 256 bits of entropy."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def build_record_name(hostname: str) -> str:
    """The fully-qualified TXT record name the caller must create."""
    return f"{_RECORD_NAME_PREFIX}.{hostname}"


def build_control_record_name(hostname: str, nonce: str) -> str:
    """A sibling record name used to detect a wildcard TXT at the same level."""
    return f"{_RECORD_NAME_PREFIX}-{nonce}.{hostname}"


def build_record_value(token: str) -> str:
    """The exact TXT value the caller must publish for ``token``."""
    return f"{_RECORD_VALUE_PREFIX}{token}"


def digest_value(value: str) -> str:
    """SHA-256 hex digest of a TXT value. Never store the raw value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def matches_digest(value: str, expected_digest: str) -> bool:
    """Constant-time comparison of ``value``'s digest against the stored one."""
    return hmac.compare_digest(digest_value(value), expected_digest)


def token_last_four(token: str) -> str:
    """The last four characters of the token, safe to display."""
    return token[-4:]
