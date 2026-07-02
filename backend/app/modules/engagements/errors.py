"""Engagement domain errors."""

from app.platform.errors import ConflictError, DomainValidationError, NotFoundError


class EngagementNotFound(NotFoundError):
    """No engagement with this id is visible to the caller's tenant."""

    code = "engagement_not_found"


class InvalidEngagementStateTransition(ConflictError):
    """The requested transition is not allowed from the current status."""

    code = "invalid_engagement_state_transition"


class EngagementImmutableError(ConflictError):
    """A mutation was attempted on an engagement in a terminal state."""

    code = "engagement_immutable"


class InvalidEngagementTimeRange(DomainValidationError):
    """starts_at must be before ends_at and within the maximum duration."""

    code = "invalid_engagement_time_range"


class InvalidEngagementScope(DomainValidationError):
    """One or more asset scopes do not satisfy the domain rules."""

    code = "invalid_engagement_scope"


class AuthorizationNotValidForEngagement(ConflictError):
    """The linked authorization is not in a valid state for the operation."""

    code = "authorization_not_valid_for_engagement"


class EngagementActivationBlocked(DomainValidationError):
    """Activation is blocked by a domain rule."""

    code = "engagement_activation_blocked"


class KillSwitchImmutableError(ConflictError):
    """The kill switch cannot be modified for an engagement in a terminal state."""

    code = "kill_switch_immutable"
