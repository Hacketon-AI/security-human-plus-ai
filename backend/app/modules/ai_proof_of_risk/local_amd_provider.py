import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from app.config import Settings
from app.modules.ai_proof_of_risk.enums import (
    ProviderStatus,
)
from app.modules.ai_proof_of_risk.fireworks_provider import HTTPClient
from app.modules.ai_proof_of_risk.prompt_templates import (
    CHECK_EVIDENCE_SUFFICIENCY_PROMPT,
    CLASSIFY_FINDING_COMPLEXITY_PROMPT,
    GENERATE_SHORT_REMEDIATION_HINT_PROMPT,
    SAFETY_INSTRUCTIONS,
    SUGGEST_ROUTE_PROMPT,
    SUMMARIZE_SIMPLE_FINDING_PROMPT,
)
from app.modules.ai_proof_of_risk.providers import AIProvider
from app.modules.ai_proof_of_risk.schemas import (
    ComplexityClassification,
    EvidenceSufficiencyResult,
    ProviderHealthStatus,
    RemediationHint,
    RouteSuggestion,
    SafeSummary,
)

logger = logging.getLogger(__name__)


class LocalAmdModelProvider(AIProvider):
    """Local AMD ROCm Model Provider for token-efficient reasoning tasks.

    This provider acts as the first line of intelligent routing and
    classification.
    """

    def __init__(self, config: Settings, http_client: HTTPClient) -> None:
        self.config = config
        self.http_client = http_client

    @property
    def provider_name(self) -> str:
        return "local_amd_model"

    @property
    def model_name(self) -> str:
        return self.config.ai_local_amd_model_name or "unknown"

    def analyze(self, sanitized_evidence: dict[str, object]) -> dict[str, object]:
        return {}

    def health(self) -> ProviderHealthStatus:
        if not self.config.ai_local_amd_enabled:
            return ProviderHealthStatus(
                provider_name=self.provider_name,
                status=ProviderStatus.unavailable,
                model_name=self.model_name,
            )

        if not self.config.ai_local_amd_base_url:
            return ProviderHealthStatus(
                provider_name=self.provider_name,
                status=ProviderStatus.unavailable,
                model_name=self.model_name,
            )

        try:
            parsed_url = urllib.parse.urlparse(self.config.ai_local_amd_base_url)
            if parsed_url.scheme not in ("http", "https"):
                return ProviderHealthStatus(
                    provider_name=self.provider_name,
                    status=ProviderStatus.unavailable,
                    model_name=self.model_name,
                )
        except Exception:
            return ProviderHealthStatus(
                provider_name=self.provider_name,
                status=ProviderStatus.unavailable,
                model_name=self.model_name,
            )

        return ProviderHealthStatus(
            provider_name=self.provider_name,
            status=ProviderStatus.available,
            model_name=self.model_name,
        )

    def _is_safe_json(self, response_text: str) -> bool:
        """Reject obvious exploit commands in local model output."""
        dangerous_strings = [
            "curl ",
            "wget ",
            "bash -i",
            "nc -e",
            "eval(",
            "os.system",
            "subprocess",
            "<script>",
        ]
        text_lower = response_text.lower()
        return not any(ds in text_lower for ds in dangerous_strings)

    def _call_model(self, prompt: str) -> dict[str, Any] | None:
        if self.health().status is not ProviderStatus.available:
            return None

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.config.ai_local_amd_max_tokens,
            "temperature": self.config.ai_local_amd_temperature,
            "response_format": {"type": "json_object"},
        }

        url = self.config.ai_local_amd_base_url
        if not url:
            return None

        try:
            response = self.http_client.post(
                url,
                json_data=payload,
                headers=headers,
                timeout=self.config.ai_local_amd_timeout_seconds,
            )
            content = (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )

            if not content or not self._is_safe_json(content):
                logger.warning("Unsafe output detected from local AMD model.")
                return None

            return dict(json.loads(content))
        except Exception as e:
            logger.warning(f"Local AMD model call failed: {e}")
            return None

    def classify_finding_complexity(
        self, sanitized_finding_summary: dict[str, Any]
    ) -> ComplexityClassification | None:
        prompt = (
            f"{SAFETY_INSTRUCTIONS}\n\n"
            f"{CLASSIFY_FINDING_COMPLEXITY_PROMPT}\n\n"
            f"Finding: {json.dumps(sanitized_finding_summary)}\n"
        )
        res = self._call_model(prompt)
        if not res:
            return None
        try:
            return ComplexityClassification.model_validate(res)
        except Exception:
            return None

    def suggest_route(
        self, analysis_mode: str, finding_summary: dict[str, Any]
    ) -> RouteSuggestion | None:
        prompt = (
            f"{SAFETY_INSTRUCTIONS}\n\n"
            f"{SUGGEST_ROUTE_PROMPT}\n\n"
            f"Mode: {analysis_mode}\n"
            f"Finding: {json.dumps(finding_summary)}\n"
        )
        res = self._call_model(prompt)
        if not res:
            return None
        try:
            return RouteSuggestion.model_validate(res)
        except Exception:
            return None

    def summarize_simple_finding(
        self, sanitized_finding_summary: dict[str, Any]
    ) -> SafeSummary | None:
        prompt = (
            f"{SAFETY_INSTRUCTIONS}\n\n"
            f"{SUMMARIZE_SIMPLE_FINDING_PROMPT}\n\n"
            f"Finding: {json.dumps(sanitized_finding_summary)}\n"
        )
        res = self._call_model(prompt)
        if not res:
            return None
        try:
            return SafeSummary.model_validate(res)
        except Exception:
            return None

    def check_evidence_sufficiency(
        self, sanitized_evidence_summary: dict[str, Any]
    ) -> EvidenceSufficiencyResult | None:
        prompt = (
            f"{SAFETY_INSTRUCTIONS}\n\n"
            f"{CHECK_EVIDENCE_SUFFICIENCY_PROMPT}\n\n"
            f"Evidence: {json.dumps(sanitized_evidence_summary)}\n"
        )
        res = self._call_model(prompt)
        if not res:
            return None
        try:
            return EvidenceSufficiencyResult.model_validate(res)
        except Exception:
            return None

    def generate_short_remediation_hint(
        self, sanitized_finding_summary: dict[str, Any]
    ) -> RemediationHint | None:
        prompt = (
            f"{SAFETY_INSTRUCTIONS}\n\n"
            f"{GENERATE_SHORT_REMEDIATION_HINT_PROMPT}\n\n"
            f"Finding: {json.dumps(sanitized_finding_summary)}\n"
        )
        res = self._call_model(prompt)
        if not res:
            return None
        try:
            return RemediationHint.model_validate(res)
        except Exception:
            return None
