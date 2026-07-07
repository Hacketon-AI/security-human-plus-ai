import json
import logging
from typing import Any, Protocol

from pydantic import BaseModel, SecretStr, ValidationError

from app.modules.ai_proof_of_risk.enums import ProviderStatus
from app.modules.ai_proof_of_risk.schemas import (
    ProviderHealthStatus,
    RemediationPlan,
    RiskTribunalVerdict,
)

logger = logging.getLogger(__name__)


class HTTPClient(Protocol):
    def post(
        self,
        url: str,
        headers: dict[str, str],
        json_data: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]: ...


class DefaultHTTPClient:
    def post(
        self,
        url: str,
        headers: dict[str, str],
        json_data: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        import urllib.request

        req = urllib.request.Request(  # noqa: S310
            url,
            data=json.dumps(json_data).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            from typing import cast

            return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))


class FireworksConfig(BaseModel):
    fireworks_api_key: SecretStr | None = None
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    fireworks_model_name: str | None = None
    ai_fireworks_timeout_seconds: float = 20.0
    ai_fireworks_max_retries: int = 1
    ai_max_remote_tokens: int = 4000
    ai_temperature: float = 0.2


class FireworksGemmaReasoningProvider:
    """Real Fireworks-hosted Gemma provider for complex reasoning.

    Uses an injected HTTP client for tests without network calls.
    Enforces strict safety checks on output before parsing JSON.
    """

    def __init__(self, config: FireworksConfig, http_client: HTTPClient) -> None:
        self.config = config
        self.http_client = http_client

    @property
    def provider_name(self) -> str:
        return "fireworks_gemma"

    @property
    def model_name(self) -> str:
        return (
            self.config.fireworks_model_name
            or "accounts/fireworks/models/gemma-3-27b-it"
        )

    def health(self) -> ProviderHealthStatus:
        if not self.config.fireworks_api_key:
            return ProviderHealthStatus(
                provider_name=self.provider_name,
                status=ProviderStatus.unavailable,
                model_name=self.model_name,
            )

        import urllib.parse

        try:
            parsed_url = urllib.parse.urlparse(self.config.fireworks_base_url)
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

    def analyze(self, sanitized_evidence: dict[str, object]) -> dict[str, object]:
        return {}

    def _call_fireworks(self, prompt: str) -> dict[str, Any] | None:
        if not self.config.fireworks_api_key:
            return None

        headers = {
            "Authorization": f"Bearer {self.config.fireworks_api_key.get_secret_value()}",  # noqa: E501
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "model": self.model_name,
            "max_tokens": self.config.ai_max_remote_tokens,
            "temperature": self.config.ai_temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            response = self.http_client.post(
                url=f"{self.config.fireworks_base_url}/chat/completions",
                headers=headers,
                json_data=payload,
                timeout=self.config.ai_fireworks_timeout_seconds,
            )
        except Exception as e:
            logger.error("Fireworks API error: %s", e)
            return None

        if "choices" not in response or not response["choices"]:
            return None

        content = response["choices"][0].get("message", {}).get("content", "")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON from Fireworks Gemma response.")
            return None

        from typing import cast

        parsed = cast(dict[str, Any], parsed)

        if not self._is_safe_json(parsed):
            logger.warning("Unsafe content detected in Fireworks response")
            return None

        return parsed

    def _is_safe_json(self, parsed: Any) -> bool:
        """Reject unsafe content (shell commands, payloads, etc)."""
        text = json.dumps(parsed).lower()
        unsafe_keywords = [
            "curl ",
            "wget ",
            "nc -e",
            "/bin/sh",
            "/bin/bash",
            "exploit.py",
            "sqlmap",
            "nmap ",
            "msfconsole",
            "password=",
            "secret=",
            "harvest",
            "exfiltrate",
            "drop table",
            "delete from",
            "rm -rf",
        ]

        for keyword in unsafe_keywords:
            if keyword in text:
                return False

        # heuristic for long tokens indicating potential dumped memory
        tokens = text.split()
        for token in tokens:
            if len(token) > 1000:
                return False

        return True

    def generate_risk_tribunal(
        self,
        sanitized_evidence: dict[str, Any],
        attack_graph_summary: dict[str, Any] | None,
        digital_twin_scenario_summary: dict[str, Any] | None,
        sandbox_proof_artifact_summary: dict[str, Any] | None,
        audience: str,
        safety_instructions: str,
    ) -> RiskTribunalVerdict | None:
        prompt = (
            f"{safety_instructions}\n\n"
            f"Generate a risk tribunal verdict for audience: {audience}. "
            "Return JSON matching schema.\n"
            f"Evidence: {json.dumps(sanitized_evidence)}\n"
            f"Attack Graph: {json.dumps(attack_graph_summary)}\n"
            f"Scenario: {json.dumps(digital_twin_scenario_summary)}\n"
            f"Proof: {json.dumps(sandbox_proof_artifact_summary)}\n"
        )
        response = self._call_fireworks(prompt)
        if response is None:
            return None
        try:
            return RiskTribunalVerdict.model_validate(response)
        except ValidationError:
            return None

    def generate_remediation_plan(
        self,
        sanitized_evidence: dict[str, Any],
        attack_graph_summary: dict[str, Any] | None,
        digital_twin_scenario_summary: dict[str, Any] | None,
        sandbox_proof_artifact_summary: dict[str, Any] | None,
        audience: str,
        safety_instructions: str,
    ) -> RemediationPlan | None:
        prompt = (
            f"{safety_instructions}\n\n"
            f"Generate a remediation plan for audience: {audience}. "
            "Return JSON matching schema.\n"
            f"Evidence: {json.dumps(sanitized_evidence)}\n"
            f"Attack Graph: {json.dumps(attack_graph_summary)}\n"
            f"Scenario: {json.dumps(digital_twin_scenario_summary)}\n"
            f"Proof: {json.dumps(sandbox_proof_artifact_summary)}\n"
        )
        response = self._call_fireworks(prompt)
        if response is None:
            return None
        try:
            return RemediationPlan.model_validate(response)
        except ValidationError:
            return None

    def generate_executive_report(
        self,
        sanitized_evidence: dict[str, Any],
        attack_graph_summary: dict[str, Any] | None,
        digital_twin_scenario_summary: dict[str, Any] | None,
        sandbox_proof_artifact_summary: dict[str, Any] | None,
        audience: str,
        safety_instructions: str,
    ) -> dict[str, Any] | None:
        prompt = (
            f"{safety_instructions}\n\n"
            f"Generate an executive report summary for audience: {audience}. "
            "Return JSON with 'executive_summary' and 'technical_summary'.\n"
            f"Evidence: {json.dumps(sanitized_evidence)}\n"
            f"Attack Graph: {json.dumps(attack_graph_summary)}\n"
            f"Scenario: {json.dumps(digital_twin_scenario_summary)}\n"
            f"Proof: {json.dumps(sandbox_proof_artifact_summary)}\n"
        )
        response = self._call_fireworks(prompt)
        if response is None:
            return None
        if "executive_summary" in response and "technical_summary" in response:
            return response
        return None

    def generate_attack_graph_reasoning(
        self,
        sanitized_evidence: dict[str, Any],
        attack_graph_summary: dict[str, Any] | None,
        digital_twin_scenario_summary: dict[str, Any] | None,
        sandbox_proof_artifact_summary: dict[str, Any] | None,
        audience: str,
        safety_instructions: str,
    ) -> dict[str, Any] | None:
        prompt = (
            f"{safety_instructions}\n\n"
            f"Generate attack graph reasoning for audience: {audience}. Return JSON.\n"
            f"Evidence: {json.dumps(sanitized_evidence)}\n"
            f"Attack Graph: {json.dumps(attack_graph_summary)}\n"
            f"Scenario: {json.dumps(digital_twin_scenario_summary)}\n"
            f"Proof: {json.dumps(sandbox_proof_artifact_summary)}\n"
        )
        return self._call_fireworks(prompt)

    def generate_exploitability_hypotheses(
        self,
        sanitized_evidence: dict[str, Any],
        attack_graph_summary: dict[str, Any] | None,
        digital_twin_scenario_summary: dict[str, Any] | None,
        sandbox_proof_artifact_summary: dict[str, Any] | None,
        audience: str,
        safety_instructions: str,
    ) -> dict[str, Any] | None:
        prompt = (
            f"{safety_instructions}\n\n"
            f"Generate exploitability hypotheses for audience: {audience}. "
            "Return JSON with 'hypotheses' list.\n"
            f"Evidence: {json.dumps(sanitized_evidence)}\n"
            f"Attack Graph: {json.dumps(attack_graph_summary)}\n"
            f"Scenario: {json.dumps(digital_twin_scenario_summary)}\n"
            f"Proof: {json.dumps(sandbox_proof_artifact_summary)}\n"
        )
        return self._call_fireworks(prompt)
