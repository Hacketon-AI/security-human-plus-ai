"""Authorization domain errors."""

from app.platform.errors import ConflictError, DomainValidationError, NotFoundError


class AuthorizationNotFound(NotFoundError):
    """No authorization with this id is visible to the caller's tenant."""

    code = "authorization_not_found"


class InvalidAuthorizationStateTransition(ConflictError):
    """The requested transition is not allowed from the current status."""

    code = "invalid_authorization_state_transition"


class AuthorizationImmutableError(ConflictError):
    """A mutation was attempted on an authorization whose current status
    forbids changes."""

    code = "authorization_immutable"


class InvalidAuthorizationTimeRange(DomainValidationError):
    """valid_until must be after valid_from and within the maximum allowed
    duration."""

    code = "invalid_authorization_time_range"


class InvalidAuthorizationScope(DomainValidationError):
    """One or more asset scopes do not satisfy the domain rules:
    asset must be verified, belong to the same organization, be in the
    project, and not be suspended or retired."""

    code = "invalid_authorization_scope"


class AuthorizationActivationBlocked(DomainValidationError):
    """Activation is blocked because a required condition is not met:
    incomplete document metadata, tier_2/tier_3 without approval engine,
    core_banking flag, or production restrictions."""

    code = "authorization_activation_blocked"


class AuthorizationActivationNotConfigured(ConflictError):
    """Activation is not configured for the current environment. In
    staging/production this fails closed until the approval engine
    is wired."""

    code = "authorization_activation_not_configured"
