"""Unit tests for authorization enums."""

from app.modules.authorizations.enums import AuthorizationStatus, RiskTier


def test_status_values_are_distinct() -> None:
    values = {s.value for s in AuthorizationStatus}
    assert len(values) == len(AuthorizationStatus)


def test_risk_tier_values_are_distinct() -> None:
    values = {t.value for t in RiskTier}
    assert len(values) == len(RiskTier)


def test_risk_tier_ordering() -> None:
    """Risk tiers should reflect increasing impact level."""
    tiers = list(RiskTier)
    assert tiers[0] == RiskTier.tier_0_passive
    assert tiers[-1] == RiskTier.tier_3_critical
