"""Unit tests for executor evidence sanitization.

These pin the data-handling boundary: credential-bearing headers never appear,
token-like values are masked, and URLs lose credentials and query strings.
"""

from app.modules.validation_executions.sanitization import (
    redact_header_value,
    sanitize_response_headers,
    sanitize_url,
)


def test_authorization_and_cookies_are_dropped() -> None:
    headers = {
        "Authorization": "Bearer abcdef1234567890",
        "Cookie": "session=secret",
        "Set-Cookie": "session=secret; HttpOnly",
        "WWW-Authenticate": "Basic realm=x",
        "X-Api-Key": "k-123",
        "Content-Security-Policy": "default-src 'self'",
    }

    sanitized = sanitize_response_headers(headers)

    assert "authorization" not in sanitized
    assert "cookie" not in sanitized
    assert "set-cookie" not in sanitized
    assert "www-authenticate" not in sanitized
    assert "x-api-key" not in sanitized
    # The genuine security header survives.
    assert sanitized["content-security-policy"] == "default-src 'self'"


def test_only_surfaced_headers_are_kept() -> None:
    headers = {
        "X-Frame-Options": "DENY",
        "X-Internal-Trace": "node-7",  # not surfaced
        "Server": "nginx",  # not surfaced
    }

    sanitized = sanitize_response_headers(headers)

    assert sanitized == {"x-frame-options": "DENY"}


def test_header_matching_is_case_insensitive() -> None:
    sanitized = sanitize_response_headers({"strict-transport-security": "max-age=1"})
    assert "strict-transport-security" in sanitized

    sanitized_upper = sanitize_response_headers(
        {"STRICT-TRANSPORT-SECURITY": "max-age=1"}
    )
    assert "strict-transport-security" in sanitized_upper


def test_token_like_values_are_redacted() -> None:
    # A CSP nonce is an opaque per-response token; it must be masked in evidence.
    value = "script-src 'nonce-aGVsbG9oZWxsb2hlbGxvaGVsbG9oZWxsbw=='"
    redacted = redact_header_value(value)
    assert "aGVsbG9oZWxsb2hlbGxvaGVsbG9oZWxsbw" not in redacted
    assert "[REDACTED]" in redacted


def test_labelled_secret_is_redacted() -> None:
    redacted = redact_header_value("token=supersecretvalue")
    assert "supersecretvalue" not in redacted
    assert "[REDACTED]" in redacted


def test_header_value_length_is_bounded() -> None:
    redacted = redact_header_value("a" * 5000)
    assert len(redacted) <= 301


def test_url_credentials_are_stripped() -> None:
    cleaned = sanitize_url("https://user:pass@app.example.com/login")
    assert cleaned == "https://app.example.com/login"
    assert "user" not in cleaned
    assert "pass" not in cleaned


def test_url_query_and_fragment_are_stripped() -> None:
    cleaned = sanitize_url("https://app.example.com/cb?token=abc123#frag")
    assert cleaned == "https://app.example.com/cb"
    assert "token" not in cleaned


def test_url_port_is_preserved() -> None:
    cleaned = sanitize_url("https://app.example.com:8443/login")
    assert cleaned == "https://app.example.com:8443/login"
