import pytest
from app.modules.ai_proof_of_risk.errors import UnsafeEvidenceForAI
from app.modules.ai_proof_of_risk.redaction import redact_evidence
from app.modules.ai_proof_of_risk.safety_policy import assert_evidence_safe_for_ai


def test_authorization_header_is_redacted() -> None:
    result = redact_evidence({"headers": {"Authorization": "Bearer abc123def456"}})

    sanitized_headers = result.sanitized_evidence.get("headers")
    assert isinstance(sanitized_headers, dict)
    assert "Authorization" not in sanitized_headers
    assert "headers.Authorization" in result.removed_fields


def test_cookie_header_is_redacted() -> None:
    result = redact_evidence({"headers": {"Cookie": "session=secret"}})

    sanitized_headers = result.sanitized_evidence.get("headers")
    assert isinstance(sanitized_headers, dict)
    assert "Cookie" not in sanitized_headers
    assert "headers.Cookie" in result.removed_fields


def test_set_cookie_header_is_redacted() -> None:
    result = redact_evidence({"headers": {"Set-Cookie": "session=secret; HttpOnly"}})

    sanitized_headers = result.sanitized_evidence.get("headers")
    assert isinstance(sanitized_headers, dict)
    assert "Set-Cookie" not in sanitized_headers
    assert "headers.Set-Cookie" in result.removed_fields


def test_raw_request_body_is_removed() -> None:
    result = redact_evidence({"raw_request_body": "<html>...</html>"})

    assert "raw_request_body" not in result.sanitized_evidence
    assert "raw_request_body" in result.removed_fields


def test_raw_response_body_is_removed() -> None:
    result = redact_evidence({"raw_response_body": "<html>...</html>"})

    assert "raw_response_body" not in result.sanitized_evidence
    assert "raw_response_body" in result.removed_fields


def test_worker_credential_token_is_removed() -> None:
    result = redact_evidence({"worker_credential_raw_token": "tok_abc123"})

    assert "worker_credential_raw_token" not in result.sanitized_evidence
    assert "worker_credential_raw_token" in result.removed_fields


def test_broker_url_is_removed() -> None:
    result = redact_evidence({"broker_url": "amqp://user:pass@rabbit:5672"})

    assert "broker_url" not in result.sanitized_evidence
    assert "broker_url" in result.removed_fields


def test_database_url_is_removed() -> None:
    result = redact_evidence({"database_url": "postgresql://user:pass@db:5432/app"})

    assert "database_url" not in result.sanitized_evidence
    assert "database_url" in result.removed_fields


def test_kill_switch_token_is_removed() -> None:
    result = redact_evidence({"kill_switch_token": "ks-token-abc"})

    assert "kill_switch_token" not in result.sanitized_evidence
    assert "kill_switch_token" in result.removed_fields


def test_jwt_value_is_redacted_in_string() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.abc123def456ghi"
    result = redact_evidence({"some_field": f"token is {jwt}"})

    sanitized_value = result.sanitized_evidence["some_field"]
    assert isinstance(sanitized_value, str)
    assert jwt not in sanitized_value
    assert "[REDACTED]" in sanitized_value


def test_private_key_is_redacted() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpA...\n-----END RSA PRIVATE KEY-----"
    result = redact_evidence({"config": pem})

    sanitized_value = result.sanitized_evidence["config"]
    assert isinstance(sanitized_value, str)
    assert "BEGIN RSA PRIVATE KEY" not in sanitized_value
    assert "[REDACTED]" in sanitized_value


def test_opaque_long_secret_is_redacted() -> None:
    secret = "aVeryLongBase64SecretValueThatIsMoreThan32Characters"
    result = redact_evidence({"token_field": secret})

    sanitized_value = result.sanitized_evidence["token_field"]
    assert isinstance(sanitized_value, str)
    assert secret not in sanitized_value
    assert "[REDACTED]" in sanitized_value


def test_safe_security_headers_pass_through() -> None:
    result = redact_evidence(
        {
            "headers": {
                "Content-Security-Policy": "default-src 'self'",
                "X-Frame-Options": "DENY",
            }
        }
    )

    sanitized_headers = result.sanitized_evidence.get("headers")
    assert isinstance(sanitized_headers, dict)
    assert sanitized_headers["Content-Security-Policy"] == "default-src 'self'"
    assert sanitized_headers["X-Frame-Options"] == "DENY"


def test_redaction_summary_has_entries() -> None:
    result = redact_evidence(
        {
            "headers": {"Authorization": "Bearer token123"},
            "raw_request_body": "<html>body</html>",
            "broker_url": "amqp://user:pass@host:5672",
        }
    )

    assert len(result.redaction_summary) >= 3
    field_paths = {entry.field_path for entry in result.redaction_summary}
    assert "headers.Authorization" in field_paths
    assert "raw_request_body" in field_paths
    assert "broker_url" in field_paths


def test_safety_policy_rejects_bearer_in_evidence() -> None:
    evidence: dict[str, object] = {
        "some_field": "Bearer abc123def456_secret_token",
    }

    with pytest.raises(UnsafeEvidenceForAI):
        assert_evidence_safe_for_ai(evidence)
