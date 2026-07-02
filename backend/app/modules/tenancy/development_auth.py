"""Development-only tenant authentication adapter.

This is NOT production authentication. It resolves the tenant from an explicit
``X-Organization-Id`` request header so the control plane can be exercised in
development and tests before an OIDC/SSO identity provider is integrated.

It is active only when ``Settings.development_auth_active`` is true (development
or test, unless explicitly disabled). In staging or production it fails closed:
the header is ignored and the request is refused with a "not configured" error.
The tenant is read only from this header — never from the request body, query
string, or cookies — so a client cannot assert ownership of another tenant.

Replace this adapter with a real identity provider before any non-development
deployment; do not extend it into a full auth system here.
"""

from uuid import UUID

from fastapi import Depends, Header

from app.config import Settings
from app.modules.tenancy.context import TenantContext
from app.platform.dependencies import get_app_settings
from app.platform.errors import AuthenticationRequiredError, ServiceNotConfiguredError

_TENANT_HEADER = "X-Organization-Id"


class TenantContextMissing(AuthenticationRequiredError):
    """The request carried no usable tenant context header."""

    code = "tenant_context_missing"


class TenantAuthenticationNotConfigured(ServiceNotConfiguredError):
    """No tenant authentication is configured for this environment.

    Raised when the development adapter is inactive (staging/production) and no
    production identity provider has been wired yet, so tenant-scoped endpoints
    fail closed instead of trusting a development header.
    """

    code = "tenant_authentication_not_configured"


async def require_tenant_context(
    x_organization_id: str | None = Header(default=None, alias=_TENANT_HEADER),
    settings: Settings = Depends(get_app_settings),
) -> TenantContext:
    """Resolve the tenant context, or fail closed.

    Refuses outside development/test, ignores the header there, and rejects a
    missing or malformed header within development/test.
    """
    if not settings.development_auth_active:
        raise TenantAuthenticationNotConfigured(
            "tenant authentication is not configured for this environment"
        )
    if x_organization_id is None:
        raise TenantContextMissing("missing tenant context")
    try:
        organization_id = UUID(x_organization_id)
    except ValueError as exc:
        raise TenantContextMissing("malformed tenant context") from exc
    return TenantContext(organization_id=organization_id)
