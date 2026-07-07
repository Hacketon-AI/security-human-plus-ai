"""AI provider abstractions and fake implementations for tests.

Step 1 provides only fake (deterministic) providers. Real Fireworks API calls
and AMD/ROCm local model serving are deferred to later steps. The provider
protocol defines the contract that real implementations will satisfy.

No live network calls are made. No secrets are handled.
"""

from typing import Protocol

from app.modules.ai_proof_of_risk.enums import ProviderStatus
from app.modules.ai_proof_of_risk.schemas import ProviderHealthStatus


class AIProvider(Protocol):
    """Contract for an AI provider backend.

    Implementations must be stateless with respect to secrets — they receive
    only sanitized evidence and return structured analysis. The ``health``
    method reports availability without performing inference.
    """

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def health(self) -> ProviderHealthStatus: ...

    def analyze(self, sanitized_evidence: dict[str, object]) -> dict[str, object]: ...


class FakeRuleOnlyProvider:
    """Deterministic rule-based provider for simple header findings.

    Returns canned analysis keyed by finding type. No model inference.
    """

    @property
    def provider_name(self) -> str:
        return "rule_only"

    @property
    def model_name(self) -> str:
        return "deterministic_rules_v1"

    def health(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider_name=self.provider_name,
            status=ProviderStatus.available,
            model_name=self.model_name,
        )

    def analyze(self, sanitized_evidence: dict[str, object]) -> dict[str, object]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "analysis_type": "rule_based",
            "result": "deterministic_analysis_complete",
        }


class FakeAMDLocalProvider:
    """Fake AMD/ROCm local model provider for medium classification.

    Simulates a local GPU inference endpoint. Returns deterministic results.
    Real AMD Developer Cloud integration is deferred to a later step.
    """

    def __init__(self, *, available: bool = True) -> None:
        self._available = available

    @property
    def provider_name(self) -> str:
        return "local_amd_model"

    @property
    def model_name(self) -> str:
        return "gemma-3-4b-rocm-local"

    def health(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider_name=self.provider_name,
            status=ProviderStatus.available
            if self._available
            else ProviderStatus.unavailable,
            model_name=self.model_name,
        )

    def analyze(self, sanitized_evidence: dict[str, object]) -> dict[str, object]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "analysis_type": "classification",
            "result": "fake_amd_classification_complete",
        }


class FakeFireworksGemmaProvider:
    """Fake Fireworks-hosted Gemma provider for complex reasoning.

    Simulates the Fireworks API. Returns deterministic results. Real Fireworks
    API integration is deferred to a later step.
    """

    def __init__(self, *, available: bool = True) -> None:
        self._available = available

    @property
    def provider_name(self) -> str:
        return "fireworks_gemma"

    @property
    def model_name(self) -> str:
        return "gemma-3-27b-it-fireworks"

    def health(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider_name=self.provider_name,
            status=ProviderStatus.available
            if self._available
            else ProviderStatus.unavailable,
            model_name=self.model_name,
        )

    def analyze(self, sanitized_evidence: dict[str, object]) -> dict[str, object]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "analysis_type": "reasoning",
            "result": "fake_fireworks_reasoning_complete",
        }
