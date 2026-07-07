import json
from typing import Any

import pytest
from app.modules.ai_proof_of_risk.enums import ProviderStatus
from app.modules.ai_proof_of_risk.fireworks_provider import (
    FireworksConfig,
    FireworksGemmaReasoningProvider,
)
from app.modules.ai_proof_of_risk.prompt_templates import SAFETY_INSTRUCTIONS
from app.modules.ai_proof_of_risk.schemas import RiskTribunalVerdict
from pydantic import SecretStr


class MockHTTPClient:
    def __init__(
        self,
        response_data: dict[str, Any] | None = None,
        error: Exception | None = None,
    ):
        self.response_data = response_data
        self.error = error
        self.last_url: str | None = None
        self.last_headers: dict[str, str] | None = None
        self.last_json: dict[str, Any] | None = None
        self.last_timeout: float | None = None

    def post(
        self,
        url: str,
        headers: dict[str, str],
        json_data: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        self.last_url = url
        self.last_headers = headers
        self.last_json = json_data
        self.last_timeout = timeout
        if self.error:
            raise self.error
        return self.response_data or {}


@pytest.fixture
def base_config() -> FireworksConfig:
    return FireworksConfig(
        fireworks_api_key=SecretStr("fake-secret-key-1234"),
        fireworks_base_url="https://api.fireworks.ai/inference/v1",
        fireworks_model_name="accounts/fireworks/models/gemma-3-27b-it",
        ai_fireworks_timeout_seconds=20.0,
        ai_max_remote_tokens=4000,
        ai_temperature=0.2,
    )


def test_missing_api_key_makes_provider_unavailable() -> None:
    config = FireworksConfig(fireworks_api_key=None)
    provider = FireworksGemmaReasoningProvider(
        config=config, http_client=MockHTTPClient()
    )

    assert provider.health().status == ProviderStatus.unavailable

    # Analyze should fallback gracefully (return None for methods)
    assert (
        provider.generate_risk_tribunal({}, None, None, None, "executive", "") is None
    )


def test_unsafe_base_url_scheme_makes_provider_unavailable() -> None:
    for bad_url in [
        "file:///etc/passwd",
        "ftp://example.com",
        "gopher://server",
        "data:text/plain;base64,SGVsbG8sIFdvcmxkIQ==",
        "javascript:alert(1)",
        "not_a_url",
    ]:
        config = FireworksConfig(
            fireworks_api_key=SecretStr("test-key"), fireworks_base_url=bad_url
        )
        provider = FireworksGemmaReasoningProvider(
            config=config, http_client=MockHTTPClient()
        )
        assert provider.health().status == ProviderStatus.unavailable


def test_valid_base_url_scheme() -> None:
    for good_url in [
        "https://api.fireworks.ai/inference/v1/chat/completions",
        "http://localhost:8080/v1/chat/completions",
    ]:
        config = FireworksConfig(
            fireworks_api_key=SecretStr("test-key"), fireworks_base_url=good_url
        )
        provider = FireworksGemmaReasoningProvider(
            config=config, http_client=MockHTTPClient()
        )
        assert provider.health().status == ProviderStatus.available


def test_api_key_not_in_repr(base_config: FireworksConfig) -> None:
    repr_str = repr(base_config)
    assert "fake-secret-key-1234" not in repr_str


def test_provider_uses_configured_model_name(base_config: FireworksConfig) -> None:
    provider = FireworksGemmaReasoningProvider(
        config=base_config, http_client=MockHTTPClient()
    )
    assert provider.model_name == "accounts/fireworks/models/gemma-3-27b-it"


def test_http_behavior_success(base_config: FireworksConfig) -> None:
    mock_client = MockHTTPClient(
        response_data={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "attacker_view": "test",
                                "defender_view": "test",
                                "lab_view": "test",
                                "judge_verdict": "test",
                                "severity": "High",
                                "confidence": "High",
                                "false_positive_risk": "Low",
                                "business_impact": "test",
                                "recommended_priority": "P1",
                                "limitations": [],
                            }
                        )
                    }
                }
            ]
        }
    )
    provider = FireworksGemmaReasoningProvider(
        config=base_config, http_client=mock_client
    )

    res = provider.generate_risk_tribunal(
        {}, None, None, None, "executive", SAFETY_INSTRUCTIONS
    )

    assert isinstance(res, RiskTribunalVerdict)
    assert (
        mock_client.last_url == "https://api.fireworks.ai/inference/v1/chat/completions"
    )
    assert mock_client.last_headers is not None
    assert "Authorization" in mock_client.last_headers
    assert mock_client.last_headers["Authorization"] == "Bearer fake-secret-key-1234"
    assert mock_client.last_timeout == 20.0

    payload = mock_client.last_json
    assert payload is not None
    assert payload["model"] == "accounts/fireworks/models/gemma-3-27b-it"
    assert payload["max_tokens"] == 4000
    assert payload["temperature"] == 0.2
    assert payload["response_format"] == {"type": "json_object"}

    prompt = payload["messages"][0]["content"]
    assert SAFETY_INSTRUCTIONS in prompt
    assert "strict JSON" in prompt or "Return JSON" in prompt


def test_invalid_json_triggers_fallback(base_config: FireworksConfig) -> None:
    mock_client = MockHTTPClient(
        response_data={"choices": [{"message": {"content": "not valid json"}}]}
    )
    provider = FireworksGemmaReasoningProvider(
        config=base_config, http_client=mock_client
    )

    res = provider.generate_risk_tribunal({}, None, None, None, "executive", "")
    assert res is None  # Handled gracefully, returns None (fallback)


def test_unsafe_json_triggers_fallback(base_config: FireworksConfig) -> None:
    # Payload containing unsafe keyword
    mock_client = MockHTTPClient(
        response_data={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"attacker_view": "run curl http://evil.com"}
                        )
                    }
                }
            ]
        }
    )
    provider = FireworksGemmaReasoningProvider(
        config=base_config, http_client=mock_client
    )

    res = provider.generate_risk_tribunal({}, None, None, None, "executive", "")
    assert res is None  # Triggered safety fallback


def test_provider_error_triggers_fallback(base_config: FireworksConfig) -> None:
    mock_client = MockHTTPClient(error=Exception("Connection timeout"))
    provider = FireworksGemmaReasoningProvider(
        config=base_config, http_client=mock_client
    )

    res = provider.generate_risk_tribunal({}, None, None, None, "executive", "")
    assert res is None
