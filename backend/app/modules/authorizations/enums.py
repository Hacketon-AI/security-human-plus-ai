"""Authorization domain enumerations."""

from enum import StrEnum


class AuthorizationStatus(StrEnum):
    """Lifecycle of a written security-testing authorization.

    ``draft`` is editable. ``submitted`` is immutable except for activation
    or rejection. ``active`` is immutable for scope, time, risk tier, and
    limits — changes require revocation and a new authorization. ``expired``,
    ``revoked``, and ``rejected`` are terminal.
    """

    draft = "draft"
    submitted = "submitted"
    active = "active"
    expired = "expired"
    revoked = "revoked"
    rejected = "rejected"


class RiskTier(StrEnum):
    """Maximum risk tier permitted under an authorization.

    ``tier_0_passive``: passive observation only (default fallback).
    ``tier_1_safe``: safe, low-impact active checks.
    ``tier_2_controlled``: controlled-impact techniques (requires approval engine).
    ``tier_3_critical``: critical techniques (requires approval engine).
    """

    tier_0_passive = "tier_0_passive"
    tier_1_safe = "tier_1_safe"
    tier_2_controlled = "tier_2_controlled"
    tier_3_critical = "tier_3_critical"
