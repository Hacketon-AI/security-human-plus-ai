"""Domain error taxonomy for the control plane.

Modules raise specific subclasses at their boundaries; the API layer maps these
to typed responses (see ``app.platform.error_handlers``). The semantic bases
below let that mapping stay small: it keys off the category, not every concrete
error. Domain errors must never carry unmasked sensitive data in their message
(see ``.claude/rules/data-handling.md``).
"""

from typing import ClassVar


class SecureScopeError(Exception):
    """Base class for all SecureScope domain errors.

    ``code`` is a stable, machine-readable identifier returned to API clients;
    it never contains sensitive data.
    """

    code: ClassVar[str] = "error"


class NotFoundError(SecureScopeError):
    """A requested resource does not exist, or is not visible to the caller.

    Cross-tenant access maps here on purpose: a resource owned by another
    tenant is indistinguishable from one that does not exist.
    """

    code: ClassVar[str] = "not_found"


class ConflictError(SecureScopeError):
    """The request conflicts with the current state (uniqueness or lifecycle)."""

    code: ClassVar[str] = "conflict"


class DomainValidationError(SecureScopeError):
    """External input is well-formed but violates a domain rule."""

    code: ClassVar[str] = "validation_error"


class AuthenticationRequiredError(SecureScopeError):
    """The caller did not present a usable tenant/identity context."""

    code: ClassVar[str] = "authentication_required"


class ServiceNotConfiguredError(SecureScopeError):
    """A required capability is not configured for the current environment.

    Used to fail closed where a production identity or authorization mechanism
    is intentionally not yet wired: the operation is refused (HTTP 501) rather
    than served by a fake or default credential.
    """

    code: ClassVar[str] = "service_not_configured"
