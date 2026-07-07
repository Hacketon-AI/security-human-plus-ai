from app.config import Settings
from app.modules.ai_proof_of_risk.enums import ProviderStatus
from app.modules.ai_proof_of_risk.local_amd_provider import LocalAmdModelProvider


class MockHTTPClient:
    def __init__(
        self, response_content: str = "{}", error: Exception | None = None
    ) -> None:
        self.response_content = response_content
        self.error = error
        self.called_urls: list[str] = []

    from typing import Any

    def post(
        self,
        url: str,
        headers: dict[str, Any],
        json_data: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        self.called_urls.append(url)
        if self.error:
            raise self.error
        return {"choices": [{"message": {"content": self.response_content}}]}


def test_amd_local_provider_health_check_disabled() -> None:
    config = Settings(ai_local_amd_enabled=False)
    client = MockHTTPClient()
    provider = LocalAmdModelProvider(config, client)

    health = provider.health()
    assert health.status == ProviderStatus.unavailable
    assert health.provider_name == "local_amd_model"


def test_amd_local_provider_health_check_no_url() -> None:
    config = Settings(ai_local_amd_enabled=True, ai_local_amd_base_url=None)
    client = MockHTTPClient()
    provider = LocalAmdModelProvider(config, client)

    health = provider.health()
    assert health.status == ProviderStatus.unavailable


def test_amd_local_provider_health_check_invalid_scheme() -> None:
    config = Settings(
        ai_local_amd_enabled=True, ai_local_amd_base_url="file:///etc/passwd"
    )
    client = MockHTTPClient()
    provider = LocalAmdModelProvider(config, client)

    health = provider.health()
    assert health.status == ProviderStatus.unavailable


def test_amd_local_provider_health_check_available() -> None:
    config = Settings(
        ai_local_amd_enabled=True,
        ai_local_amd_base_url="http://localhost:8080/v1/chat/completions",
        ai_local_amd_model_name="gemma-3",
    )
    client = MockHTTPClient()
    provider = LocalAmdModelProvider(config, client)

    health = provider.health()
    assert health.status == ProviderStatus.available
    assert health.model_name == "gemma-3"


def test_amd_local_provider_unsafe_output_rejected() -> None:
    config = Settings(
        ai_local_amd_enabled=True,
        ai_local_amd_base_url="http://localhost:8080/v1/chat/completions",
    )
    client = MockHTTPClient(response_content='{"summary": "run bash -i"}')
    provider = LocalAmdModelProvider(config, client)

    res = provider.summarize_simple_finding({"test": "data"})
    assert res is None


def test_amd_local_provider_valid_summary() -> None:
    config = Settings(
        ai_local_amd_enabled=True,
        ai_local_amd_base_url="http://localhost:8080/v1/chat/completions",
    )
    client = MockHTTPClient(response_content='{"summary": "safe summary"}')
    provider = LocalAmdModelProvider(config, client)

    res = provider.summarize_simple_finding({"test": "data"})
    assert res is not None
    assert res.summary == "safe summary"


def test_amd_local_provider_network_error() -> None:
    config = Settings(
        ai_local_amd_enabled=True,
        ai_local_amd_base_url="http://localhost:8080/v1/chat/completions",
    )
    client = MockHTTPClient(error=Exception("Connection refused"))
    provider = LocalAmdModelProvider(config, client)

    res = provider.summarize_simple_finding({"test": "data"})
    assert res is None
