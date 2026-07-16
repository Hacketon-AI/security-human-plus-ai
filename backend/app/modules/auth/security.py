"""Password hashing and JWT token utilities."""

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

# PBKDF2-SHA256 is intentionally used to avoid adding a password-hashing
# dependency. The iteration count follows current OWASP guidance for PBKDF2.
_PBKDF2_ITERATIONS = 600_000
_SALT_LENGTH = 32
_HASH_LENGTH = 64
_DEFAULT_EXPIRY_HOURS = 24
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-SHA256."""
    salt = os.urandom(_SALT_LENGTH)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_HASH_LENGTH,
    )
    return f"{salt.hex()}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    try:
        salt_hex, hash_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
    except (AttributeError, ValueError):
        return False

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_HASH_LENGTH,
    )
    return hmac.compare_digest(password_hash, expected_hash)


def create_access_token(
    *,
    user_id: str,
    email: str,
    role: str,
    organization_id: str | None,
    token_version: int,
    secret_key: str,
    expires_hours: int = _DEFAULT_EXPIRY_HOURS,
) -> tuple[str, int]:
    """Create a versioned access token and return it with its lifetime."""
    now = datetime.now(UTC)
    expires_delta = timedelta(hours=expires_hours)
    expire = now + expires_delta
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "role": role,
        "org_id": organization_id,
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    token = jwt.encode(payload, secret_key, algorithm=_ALGORITHM)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str, secret_key: str) -> dict[str, Any] | None:
    """Decode and verify an access token, returning ``None`` if invalid."""
    try:
        payload: dict[str, Any] = jwt.decode(token, secret_key, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "access":
        return None
    return payload
