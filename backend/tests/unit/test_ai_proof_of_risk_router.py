"""Unit tests for AI Proof-of-Risk security router."""

import uuid

from app.modules.ai_proof_of_risk.enums import AIRoute, FindingComplexity
from app.modules.ai_proof_of_risk.providers import (
    AIProvider,
    FakeAMDLocalProvider,
    FakeFireworksGemmaProvider,
    FakeRuleOnlyProvider,
)
from app.modules.ai_proof_of_risk.schemas import RoutingRequest
from app.modules.ai_proof_of_risk.security_router import route_finding

_EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_request(
    *,
    complexity: FindingComplexity = FindingComplexity.simple,
    finding_type: str = "missing_csp",
) -> RoutingRequest:
    return RoutingRequest(
        execution_id=_EXECUTION_ID,
        finding_id="f1",
        finding_type=finding_type,
        complexity=complexity,
        sanitized_evidence={},
    )


def _all_providers_available() -> dict[str, AIProvider]:
    return {
        "rule_only": FakeRuleOnlyProvider(),
        "local_amd_model": FakeAMDLocalProvider(available=True),
        "fireworks_gemma": FakeFireworksGemmaProvider(available=True),
    }


def test_simple_known_finding_routes_to_rule_only() -> None:
    request = _make_request(
        complexity=FindingComplexity.simple, finding_type="missing_csp"
    )
    decision = route_finding(request, providers=_all_providers_available())

    assert decision.selected_route is AIRoute.rule_only


def test_medium_finding_routes_to_amd_local() -> None:
    request = _make_request(
        complexity=FindingComplexity.medium, finding_type="custom_finding"
    )
    decision = route_finding(request, providers=_all_providers_available())

    assert decision.selected_route is AIRoute.local_amd_model


def test_complex_finding_routes_to_fireworks_gemma() -> None:
    request = _make_request(
        complexity=FindingComplexity.complex, finding_type="custom_finding"
    )
    decision = route_finding(request, providers=_all_providers_available())

    assert decision.selected_route is AIRoute.fireworks_gemma


def test_fallback_when_no_providers_available() -> None:
    request = _make_request(
        complexity=FindingComplexity.complex, finding_type="custom_finding"
    )
    providers: dict[str, AIProvider] = {
        "rule_only": FakeRuleOnlyProvider(),
        "local_amd_model": FakeAMDLocalProvider(available=False),
        "fireworks_gemma": FakeFireworksGemmaProvider(available=False),
    }
    decision = route_finding(request, providers=providers)

    assert decision.selected_route is AIRoute.deterministic_fallback


def test_medium_falls_to_fireworks_when_amd_unavailable() -> None:
    request = _make_request(
        complexity=FindingComplexity.medium, finding_type="custom_finding"
    )
    providers: dict[str, AIProvider] = {
        "rule_only": FakeRuleOnlyProvider(),
        "local_amd_model": FakeAMDLocalProvider(available=False),
        "fireworks_gemma": FakeFireworksGemmaProvider(available=True),
    }
    decision = route_finding(request, providers=providers)

    assert decision.selected_route is AIRoute.fireworks_gemma


def test_rule_only_avoids_remote_call() -> None:
    request = _make_request(
        complexity=FindingComplexity.simple, finding_type="missing_csp"
    )
    decision = route_finding(request, providers=_all_providers_available())

    assert decision.avoided_remote_call is True


def test_fireworks_does_not_avoid_remote_call() -> None:
    request = _make_request(
        complexity=FindingComplexity.complex, finding_type="custom_finding"
    )
    decision = route_finding(request, providers=_all_providers_available())

    assert decision.avoided_remote_call is False


def test_fallback_used_flag() -> None:
    request = _make_request(
        complexity=FindingComplexity.complex, finding_type="custom_finding"
    )
    providers: dict[str, AIProvider] = {
        "rule_only": FakeRuleOnlyProvider(),
        "local_amd_model": FakeAMDLocalProvider(available=False),
        "fireworks_gemma": FakeFireworksGemmaProvider(available=False),
    }
    decision = route_finding(request, providers=providers)

    assert decision.fallback_used is True

    # Non-fallback route should have fallback_used=False
    non_fallback = route_finding(
        _make_request(complexity=FindingComplexity.simple, finding_type="missing_csp"),
        providers=_all_providers_available(),
    )
    assert non_fallback.fallback_used is False
