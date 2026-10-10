"""Token-efficient security router for AI Proof-of-Risk.

Routes sanitized findings to the cheapest sufficient AI provider:
- ``rule_only`` for simple, well-known security header findings.
- ``local_amd_model`` for medium-complexity classification tasks.
- ``claude`` (preferred) or ``fireworks_gemma`` for complex report generation
  and reasoning.
- ``deterministic_fallback`` when all providers are unavailable.

The router never makes live model calls. It selects a provider based on finding
complexity and provider availability, then returns a routing decision contract.
"""

from app.modules.ai_proof_of_risk.enums import (
    AIRoute,
    AnalysisMode,
    Audience,
    FindingComplexity,
    ProviderStatus,
)
from app.modules.ai_proof_of_risk.providers import AIProvider
from app.modules.ai_proof_of_risk.schemas import RoutingDecision, RoutingRequest

# Finding types that can be fully analyzed by deterministic rules.
_RULE_ONLY_TYPES: frozenset[str] = frozenset(
    {
        "missing_csp",
        "missing_x_frame_options",
        "insecure_cookie_flags",
        "permissive_cors",
        "missing_hsts",
    }
)

# Approximate token counts for cost estimation.
_ESTIMATED_TOKENS: dict[AIRoute, tuple[int, int]] = {
    # (remote_tokens, local_tokens)
    AIRoute.rule_only: (0, 0),
    AIRoute.local_amd_model: (0, 512),
    AIRoute.claude: (2048, 0),
    AIRoute.fireworks_gemma: (2048, 0),
    AIRoute.deterministic_fallback: (0, 0),
}


def route_finding(
    request: RoutingRequest,
    *,
    providers: dict[str, AIProvider],
) -> RoutingDecision:
    """Select the cheapest sufficient provider for a finding."""

    if request.ai_router_mode == "deterministic":
        return _decision(
            route=AIRoute.deterministic_fallback,
            reason="Deterministic mode forced.",
            providers=providers,
        )

    requires_deep_reasoning = (
        request.force_remote_reasoning
        or request.audience == Audience.executive
        or request.analysis_mode
        in (AnalysisMode.full_report, AnalysisMode.risk_tribunal)
    )

    if (
        not requires_deep_reasoning
        and request.complexity is FindingComplexity.simple
        and request.finding_type in _RULE_ONLY_TYPES
    ):
        return _decision(
            route=AIRoute.rule_only,
            reason=(
                f"Finding type '{request.finding_type}' is well-known;"
                " deterministic rules suffice."
            ),
            providers=providers,
        )

    local_avail = _available(providers, "local_amd_model")
    claude_avail = _available(providers, "claude")
    remote_avail = _available(providers, "fireworks_gemma")
    needs_remote = requires_deep_reasoning or request.complexity in (
        FindingComplexity.medium,
        FindingComplexity.complex,
    )

    if request.ai_router_mode in ("hybrid", "local_only"):
        if (
            request.complexity is FindingComplexity.medium
            and not requires_deep_reasoning
        ):
            if local_avail:
                return _decision(
                    route=AIRoute.local_amd_model,
                    reason="Medium complexity finding routed to local AMD/ROCm model.",
                    providers=providers,
                )

    if request.ai_router_mode == "hybrid" and needs_remote and claude_avail:
        return _decision(
            route=AIRoute.claude,
            reason="Complex finding routed to Claude.",
            providers=providers,
        )

    if request.ai_router_mode in ("hybrid", "fireworks_only"):
        if needs_remote:
            if remote_avail:
                return _decision(
                    route=AIRoute.fireworks_gemma,
                    reason="Complex finding routed to Fireworks Gemma.",
                    providers=providers,
                )

    return _decision(
        route=AIRoute.deterministic_fallback,
        reason="No suitable provider available; using deterministic fallback.",
        providers=providers,
    )


def _decision(
    *,
    route: AIRoute,
    reason: str,
    providers: dict[str, AIProvider],
) -> RoutingDecision:
    """Build a :class:`RoutingDecision` from the selected route."""
    remote_tokens, local_tokens = _ESTIMATED_TOKENS.get(route, (0, 0))

    provider = providers.get(route.value)
    provider_name = provider.provider_name if provider else route.value
    model_name = provider.model_name if provider else "none"

    local_avail = _available(providers, "local_amd_model")
    remote_avail = _available(providers, "claude") or _available(
        providers, "fireworks_gemma"
    )

    attempted_local = route is AIRoute.local_amd_model
    attempted_remote = route in (AIRoute.claude, AIRoute.fireworks_gemma)
    avoided_remote = route in (
        AIRoute.rule_only,
        AIRoute.local_amd_model,
        AIRoute.deterministic_fallback,
    )

    token_saving = 0
    if route is AIRoute.local_amd_model:
        token_saving = 2048 - 512
    elif route is AIRoute.rule_only:
        token_saving = 2048

    fallback = route is AIRoute.deterministic_fallback
    fallback_reason = "No suitable provider available." if fallback else None

    return RoutingDecision(
        selected_route=route,
        reason=reason,
        provider_name=provider_name,
        model_name=model_name,
        local_provider_available=local_avail,
        remote_provider_available=remote_avail,
        attempted_local_call=attempted_local,
        attempted_remote_call=attempted_remote,
        avoided_remote_call=avoided_remote,
        estimated_remote_tokens=remote_tokens,
        estimated_local_tokens=local_tokens,
        token_saving_estimate=token_saving,
        fallback_used=fallback,
        fallback_reason=fallback_reason,
        local_provider_latency_ms=None,
        remote_provider_latency_ms=None,
    )


def _available(providers: dict[str, AIProvider], key: str) -> bool:
    provider = providers.get(key)
    return bool(provider and provider.health().status is ProviderStatus.available)
