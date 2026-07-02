"""Unit tests for verification token and digest helpers."""

from app.modules.asset_verifications.challenge_token import (
    build_control_record_name,
    build_record_name,
    build_record_value,
    digest_value,
    generate_token,
    matches_digest,
    token_last_four,
)


def test_generated_tokens_are_high_entropy_and_unique() -> None:
    tokens = {generate_token() for _ in range(100)}
    assert len(tokens) == 100
    # token_urlsafe(32) yields ~43 url-safe characters (256 bits of entropy).
    assert all(len(token) >= 43 for token in tokens)


def test_record_name_and_value_construction() -> None:
    assert build_record_name("www.example.com") == (
        "_securescope-verification.www.example.com"
    )
    assert build_record_value("abc123") == "securescope-verification=abc123"
    control = build_control_record_name("www.example.com", "deadbeef")
    assert control == "_securescope-verification-deadbeef.www.example.com"


def test_digest_matches_only_exact_value() -> None:
    value = build_record_value(generate_token())
    digest = digest_value(value)
    assert matches_digest(value, digest)
    assert not matches_digest(value + "x", digest)
    assert not matches_digest("securescope-verification=other", digest)


def test_digest_is_not_the_raw_value() -> None:
    token = generate_token()
    value = build_record_value(token)
    digest = digest_value(value)
    assert token not in digest
    assert value not in digest
    assert len(digest) == 64  # sha256 hex


def test_token_last_four() -> None:
    assert token_last_four("abcdef") == "cdef"
