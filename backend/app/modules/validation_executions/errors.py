"""Validation-execution domain errors."""

from app.platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)


class ValidationExecutionNotFound(NotFoundError):
    """No execution with this id is visible to the caller's tenant."""

    code = "validation_execution_not_found"


class UnknownValidationTemplate(DomainValidationError):
    """The requested template id is not registered."""

    code = "unknown_validation_template"


class ExecutionEligibilityBlocked(ConflictError):
    """A pre-dispatch eligibility rule rejected the execution request.

    Covers asset, authorization, engagement, scope, time-window, kill-switch,
    and risk-tier gates. The request is refused before anything is queued.
    """

    code = "execution_eligibility_blocked"


class InvalidExecutionScope(DomainValidationError):
    """The asset is not covered by the linked engagement or authorization
    scope, or does not satisfy the asset-state rules."""

    code = "invalid_execution_scope"


class InvalidExecutionStateTransition(ConflictError):
    """The requested transition is not allowed from the current status."""

    code = "invalid_execution_state_transition"


class ExecutionImmutableError(ConflictError):
    """A mutation was attempted on an execution in a terminal state."""

    code = "execution_immutable"


class IdempotencyConflict(ConflictError):
    """The idempotency key was already used for a materially different
    request."""

    code = "idempotency_conflict"


class WorkerAuthenticationNotConfigured(ConflictError):
    """Worker transition hooks are not configured for this environment.

    The dev/test worker adapter is inactive and no production worker identity
    has been wired, so the hooks fail closed rather than trusting an
    unauthenticated caller."""

    code = "worker_authentication_not_configured"


class WorkerCredentialIssuanceFailed(ConflictError):
    """Minting the per-execution worker credential failed at dispatch time.

    Fail-closed: the execution is never dispatched without a credential, and
    because issuance runs inside the create-and-queue transaction the whole
    request rolls back (execution row and any credential row together). The
    safe failure category is recorded server-side; the raw token and the
    internal reason are never carried in the message or the API response."""

    code = "worker_credential_issuance_failed"


class WorkerKillSwitchAuthenticationFailed(AuthenticationRequiredError):
    """The kill-switch poll presented a missing or wrong ``kill_switch_token``.

    The poll authenticates on the opaque ``kill_switch_token`` the control plane
    froze into the execution specification (see ``scan-authorization.md``), not
    the per-execution worker credential. A missing header and a token mismatch
    are intentionally indistinguishable — both surface as one 401, and the token
    value is never echoed."""

    code = "worker_kill_switch_authentication_failed"


class ValidationDispatchNotConfigured(ConflictError):
    """No execution dispatcher is configured for this environment.

    The production dispatcher is intentionally fail-closed until an isolated
    worker pipeline exists; scanners never run in the API process."""

    code = "validation_dispatch_not_configured"
