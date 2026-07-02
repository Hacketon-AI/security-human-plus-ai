"""Unit tests for validation-execution templates and risk-tier comparison."""

import pytest
from app.modules.authorizations.enums import RiskTier
from app.modules.validation_executions.errors import UnknownValidationTemplate
from app.modules.validation_executions.service import _risk_tier_lte
from app.modules.validation_executions.templates import (
    HTTP_SECURITY_HEADER_VALIDATION,
    get_template,
)


def test_known_template_is_passive_and_read_only() -> None:
    template = get_template(HTTP_SECURITY_HEADER_VALIDATION)
    assert template.risk_tier is RiskTier.tier_0_passive
    # Read-only verbs only; no payload/mutation methods.
    assert set(template.allowed_methods) <= {"HEAD", "GET"}
    # Bounded safety envelope.
    assert template.safety_limits.timeout_seconds > 0
    assert template.safety_limits.redirect_limit >= 0
    assert template.safety_limits.max_requests > 0
    assert template.safety_limits.max_response_bytes > 0


def test_unknown_template_raises() -> None:
    with pytest.raises(UnknownValidationTemplate):
        get_template("DESTRUCTIVE_TEMPLATE")


@pytest.mark.parametrize(
    "lower,higher",
    [
        (RiskTier.tier_0_passive, RiskTier.tier_0_passive),
        (RiskTier.tier_0_passive, RiskTier.tier_1_safe),
        (RiskTier.tier_1_safe, RiskTier.tier_2_controlled),
        (RiskTier.tier_2_controlled, RiskTier.tier_3_critical),
    ],
)
def test_risk_tier_lte_true(lower: RiskTier, higher: RiskTier) -> None:
    assert _risk_tier_lte(lower, higher)


@pytest.mark.parametrize(
    "higher,lower",
    [
        (RiskTier.tier_1_safe, RiskTier.tier_0_passive),
        (RiskTier.tier_2_controlled, RiskTier.tier_1_safe),
        (RiskTier.tier_3_critical, RiskTier.tier_0_passive),
    ],
)
def test_risk_tier_lte_false(higher: RiskTier, lower: RiskTier) -> None:
    assert not _risk_tier_lte(higher, lower)
