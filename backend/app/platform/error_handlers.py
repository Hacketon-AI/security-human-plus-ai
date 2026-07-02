"""Maps domain errors to typed HTTP responses at the API boundary.

Routers stay thin: they raise domain errors from services and let this central
mapping translate them. Responses carry a stable ``code`` and a safe message
only — never a stack trace, request body, or internal exception text
(see ``.claude/rules/data-handling.md``).
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
    SecureScopeError,
    ServiceNotConfiguredError,
)

# Ordered most-specific to least. The first matching category wins; anything
# that is a SecureScopeError but matches no category falls back to 400.
_STATUS_BY_CATEGORY: tuple[tuple[type[SecureScopeError], int], ...] = (
    (AuthenticationRequiredError, 401),
    (NotFoundError, 404),
    (ConflictError, 409),
    (DomainValidationError, 422),
    # A capability deliberately not wired for this environment: fail closed.
    (ServiceNotConfiguredError, 501),
)


def install_error_handlers(app: FastAPI) -> None:
    """Register the domain-error to HTTP-response mapping on ``app``."""

    async def handle_domain_error(_: Request, exc: Exception) -> JSONResponse:
        status = 400
        code = "error"
        if isinstance(exc, SecureScopeError):
            code = exc.code
            for category, mapped_status in _STATUS_BY_CATEGORY:
                if isinstance(exc, category):
                    status = mapped_status
                    break
        return JSONResponse(
            status_code=status,
            content={"error": {"code": code, "message": str(exc)}},
        )

    app.add_exception_handler(SecureScopeError, handle_domain_error)
