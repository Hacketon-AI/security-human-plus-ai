"""Claude-backed reasoning provider for AI Proof-of-Risk.

Receives only sanitized evidence (redaction happens upstream) and returns
schema-validated domain models via structured outputs. Any failure (API error,
refusal, truncation, schema mismatch, or unsafe content) returns ``None`` so
the service falls back to the next provider or to deterministic generators.
Evidence and model output are never logged.
"""

import json
import logging
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, SecretStr, ValidationError

from app.modules.ai_proof_of_risk.enums import ProviderStatus
from app.modules.ai_proof_of_risk.fireworks_provider import is_safe_model_output
from app.modules.ai_proof_of_risk.schemas import (
    ProviderHealthStatus,
    RemediationPlan,
    RiskTribunalVerdict,
)

logger = logging.getLogger(__name__)

OutputT = TypeVar("OutputT", bound=BaseModel)

_ANALYST_ROLE = (
    "You are a defensive application-security reviewer. You explain the risk "
    "of findings from an authorized, non-destructive validation run and help "
    "the asset owner fix them. Work only from the evidence provided."
)


class ClaudeConfig(BaseModel):
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5"
    timeout_seconds: float = 120.0
    max_retries: int = 2
    max_tokens: int = 16000


class ExecutiveReportSummary(BaseModel):
    executive_summary: str
    technical_summary: str


class ClaudeReasoningProvider:
    """Deep-reasoning provider using the Anthropic Messages API."""

    def __init__(
        self, config: ClaudeConfig, client: anthropic.Anthropic | None = None
    ) -> None:
        self.config = config
        if client is None and config.anthropic_api_key is not None:
            client = anthropic.Anthropic(
                api_key=config.anthropic_api_key.get_secret_value(),
                timeout=config.timeout_seconds,
                max_retries=config.max_retries,
            )
        self._client = client

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return self.config.anthropic_model

    def health(self) -> ProviderHealthStatus:
        status = (
            ProviderStatus.available
            if self._client is not None
            else ProviderStatus.unavailable
        )
        return ProviderHealthStatus(
            provider_name=self.provider_name,
            status=status,
            model_name=self.model_name,
        )

    def analyze(self, sanitized_evidence: dict[str, object]) -> dict[str, object]:
        # Protocol method used only by the router contract; real work happens in
        # the task-specific generate_* methods below.
        return {}

    def generate_risk_tribunal(
        self,
        sanitized_evidence: dict[str, Any],
        attack_graph_summary: dict[str, Any] | None,
        digital_twin_scenario_summary: dict[str, Any] | None,
        sandbox_proof_artifact_summary: list[dict[str, Any]] | None,
        audience: str,
        safety_instructions: str,
    ) -> RiskTribunalVerdict | None:
        return self._parse(
            task=(
                "Run a risk tribunal for this finding: give the attacker, "
                "defender, and lab perspectives, then a judge verdict with "
                "severity, confidence, false-positive risk, business impact, "
                "recommended priority, and limitations."
            ),
            audience=audience,
            safety_instructions=safety_instructions,
            context=_context(
                sanitized_evidence,
                attack_graph_summary,
                digital_twin_scenario_summary,
                sandbox_proof_artifact_summary,
            ),
            output_model=RiskTribunalVerdict,
        )

    def generate_remediation_plan(
        self,
        sanitized_evidence: dict[str, Any],
        attack_graph_summary: dict[str, Any] | None,
        digital_twin_scenario_summary: dict[str, Any] | None,
        sandbox_proof_artifact_summary: list[dict[str, Any]] | None,
        audience: str,
        safety_instructions: str,
    ) -> RemediationPlan | None:
        return self._parse(
            task=(
                "Write a remediation plan: the immediate fix, tasks for "
                "developers, DevOps, and the security owner, safe configuration "
                "examples, verification steps, regression tests, estimated "
                "effort, and expected risk reduction."
            ),
            audience=audience,
            safety_instructions=safety_instructions,
            context=_context(
                sanitized_evidence,
                attack_graph_summary,
                digital_twin_scenario_summary,
                sandbox_proof_artifact_summary,
            ),
            output_model=RemediationPlan,
        )

    def generate_executive_report(
        self,
        sanitized_evidence: dict[str, Any],
        attack_graph_summary: dict[str, Any] | None,
        digital_twin_scenario_summary: dict[str, Any] | None,
        sandbox_proof_artifact_summary: list[dict[str, Any]] | None,
        audience: str,
        safety_instructions: str,
    ) -> dict[str, Any] | None:
        summary = self._parse(
            task=(
                "Summarize the outcome as an executive summary for leadership "
                "and a technical summary for engineers."
            ),
            audience=audience,
            safety_instructions=safety_instructions,
            context=_context(
                sanitized_evidence,
                attack_graph_summary,
                digital_twin_scenario_summary,
                sandbox_proof_artifact_summary,
            ),
            output_model=ExecutiveReportSummary,
        )
        return summary.model_dump() if summary else None

    def _parse(
        self,
        *,
        task: str,
        audience: str,
        safety_instructions: str,
        context: str,
        output_model: type[OutputT],
    ) -> OutputT | None:
        if self._client is None:
            return None
        try:
            response = self._client.messages.parse(
                model=self.config.anthropic_model,
                max_tokens=self.config.max_tokens,
                system=f"{_ANALYST_ROLE}\n\n{safety_instructions.strip()}",
                messages=[
                    {
                        "role": "user",
                        "content": f"{task}\nAudience: {audience}.\n\n{context}",
                    }
                ],
                output_format=output_model,
            )
        except (anthropic.APIError, ValidationError) as exc:
            # Class name only: the exception text may echo request content.
            logger.warning("Claude analysis failed: %s", type(exc).__name__)
            return None

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            logger.warning("Claude declined the analysis (category=%s)", category)
            return None
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            logger.warning("Claude analysis incomplete: %s", response.stop_reason)
            return None

        parsed = response.parsed_output
        if not is_safe_model_output(parsed.model_dump()):
            logger.warning("Unsafe content detected in Claude response")
            return None
        return parsed


def _context(
    sanitized_evidence: dict[str, Any],
    attack_graph_summary: dict[str, Any] | None,
    digital_twin_scenario_summary: dict[str, Any] | None,
    sandbox_proof_artifact_summary: list[dict[str, Any]] | None,
) -> str:
    sections = {
        "sanitized_evidence": sanitized_evidence,
        "attack_graph_summary": attack_graph_summary,
        "digital_twin_scenario": digital_twin_scenario_summary,
        "sandbox_proof_artifacts": sandbox_proof_artifact_summary,
    }
    return "\n\n".join(
        f"<{name}>\n{json.dumps(value, sort_keys=True, default=str)}\n</{name}>"
        for name, value in sections.items()
        if value is not None
    )
