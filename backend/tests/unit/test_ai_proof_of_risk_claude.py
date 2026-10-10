"""Unit tests for the Claude reasoning provider and its routing priority.

No network: the Anthropic client is replaced by a fake exposing
``messages.parse``.
"""

import uuid
from types import SimpleNamespace
from typing import Any, cast

import anthropic
import httpx2
import pytest
from app.modules.ai_proof_of_risk.claude_provider import (
    ClaudeConfig,
    ClaudeReasoningProvider,
)
from app.modules.ai_proof_of_risk.enums import (
    AIRoute,
    FindingComplexity,
    ProviderStatus,
)
from app.modules.ai_proof_of_risk.providers import (
    AIProvider,
    FakeFireworksGemmaProvider,
)
from app.modules.ai_proof_of_risk.schemas import RemediationPlan, RoutingRequest
from app.modules.ai_proof_of_risk.security_router import route_finding
from pydantic import SecretStr

_PLAN = RemediationPlan(
    immediate_fix="Add Strict-Transport-Security at the gateway.",
    estimated_effort="low",
    risk_reduction="Removes protocol downgrade exposure.",
)


class _FakeMessages:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _provider(outcome: object) -> tuple[ClaudeReasoningProvider, _FakeMessages]:
    messages = _FakeMessages(outcome)
    client = cast(anthropic.Anthropic, SimpleNamespace(messages=messages))
    return ClaudeReasoningProvider(ClaudeConfig(), client=client), messages


def _response(
    stop_reason: str, parsed: object = None, category: str | None = None
) -> object:
    details = SimpleNamespace(category=category) if category else None
    return SimpleNamespace(
        stop_reason=stop_reason, stop_details=details, parsed_output=parsed
    )


def _remediation(provider: ClaudeReasoningProvider) -> RemediationPlan | None:
    return provider.generate_remediation_plan(
        sanitized_evidence={"header": "strict-transport-security", "present": False},
        attack_graph_summary=None,
        digital_twin_scenario_summary=None,
        sandbox_proof_artifact_summary=None,
        audience="technical",
        safety_instructions="Use sanitized evidence only.",
    )


def test_returns_validated_plan_and_sends_only_sanitized_context() -> None:
    provider, messages = _provider(_response("end_turn", _PLAN))

    assert _remediation(provider) == _PLAN
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_format"] is RemediationPlan
    assert "Use sanitized evidence only." in call["system"]
    assert "<sanitized_evidence>" in call["messages"][0]["content"]
    assert "attack_graph_summary" not in call["messages"][0]["content"]


@pytest.mark.parametrize(
    "outcome",
    [
        _response("refusal", category="cyber"),
        _response("max_tokens", _PLAN),
        _response("end_turn", None),
        anthropic.APIConnectionError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        ),
    ],
    ids=["refusal", "truncated", "no-parsed-output", "api-error"],
)
def test_failures_return_none_so_the_service_can_fall_back(outcome: object) -> None:
    provider, _ = _provider(outcome)
    assert _remediation(provider) is None


def test_unsafe_output_is_rejected() -> None:
    unsafe = _PLAN.model_copy(update={"immediate_fix": "run sqlmap against the target"})
    provider, _ = _provider(_response("end_turn", unsafe))
    assert _remediation(provider) is None


def test_unavailable_without_api_key() -> None:
    provider = ClaudeReasoningProvider(ClaudeConfig(anthropic_api_key=None))
    assert provider.health().status is ProviderStatus.unavailable
    assert _remediation(provider) is None


def test_available_with_api_key() -> None:
    provider = ClaudeReasoningProvider(
        ClaudeConfig(anthropic_api_key=SecretStr("sk-test"))
    )
    assert provider.health().status is ProviderStatus.available


def _routing(providers: dict[str, AIProvider]) -> AIRoute:
    request = RoutingRequest(
        execution_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        finding_id="f1",
        finding_type="custom_finding",
        complexity=FindingComplexity.complex,
        sanitized_evidence={},
    )
    return route_finding(request, providers=providers).selected_route


def test_hybrid_routing_prefers_claude_then_fireworks() -> None:
    claude_up = ClaudeReasoningProvider(
        ClaudeConfig(anthropic_api_key=SecretStr("sk-test"))
    )
    claude_down = ClaudeReasoningProvider(ClaudeConfig())
    fireworks = FakeFireworksGemmaProvider(available=True)

    assert (
        _routing({"claude": claude_up, "fireworks_gemma": fireworks}) is AIRoute.claude
    )
    assert (
        _routing({"claude": claude_down, "fireworks_gemma": fireworks})
        is AIRoute.fireworks_gemma
    )


def test_real_sdk_builds_structured_output_request_and_parses_reply() -> None:
    """Runs the actual SDK parse path over a mock transport (no network)."""
    import json

    from app.modules.ai_proof_of_risk.schemas import RiskTribunalVerdict

    verdict = {
        "attacker_view": "a",
        "defender_view": "d",
        "lab_view": "l",
        "judge_verdict": "j",
        "severity": "moderate",
        "confidence": "high",
        "false_positive_risk": "low",
        "business_impact": "b",
        "recommended_priority": "p2",
        "limitations": [],
    }
    sent: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.update(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5",
                "content": [{"type": "text", "text": json.dumps(verdict)}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = anthropic.Anthropic(
        api_key="sk-test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    provider = ClaudeReasoningProvider(ClaudeConfig(), client=client)

    result = provider.generate_risk_tribunal(
        {"x": 1}, None, None, None, "technical", "safe"
    )

    assert isinstance(result, RiskTribunalVerdict)
    assert result.severity == "moderate"
    schema = sent["output_config"]["format"]["schema"]
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False


def test_service_config_reads_router_mode_from_settings() -> None:
    """Regression: the env-configured router mode used to be ignored."""
    from app.config import Environment, Settings
    from app.modules.ai_proof_of_risk.service import ServiceConfig

    settings = Settings(
        environment=Environment.test,
        database_dsn=SecretStr("postgresql+asyncpg://t:t@localhost:5432/t"),
        ai_router_mode="hybrid",
    )
    assert ServiceConfig.from_settings(settings).ai_router_mode == "hybrid"
