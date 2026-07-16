"""Tenant authentication with a JWT primary path and local header fallback.

A verified bearer token is the tenant authority in every environment. The
``X-Organization-Id`` header remains only as an explicitly development/test
compatibility adapter when the caller supplies no bearer token.
"""

from typing import Any
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.auth.models import User
from app.modules.auth.security import decode_access_token
from app.modules.tenancy.context import TenantContext
from app.platform.dependencies import (
    get_app_settings,
    get_db_session,
    get_jwt_secret,
)
from app.platform.errors import AuthenticationRequiredError, ServiceNotConfiguredError

_TENANT_HEADER = "X-Organization-Id"


class TenantContextMissing(AuthenticationRequiredError):
    """The request carried no usable tenant identity."""

    code = "tenant_context_missing"


class TenantAuthenticationNotConfigured(ServiceNotConfiguredError):
    """No deployed tenant identity has been configured."""

    code = "tenant_authentication_not_configured"


async def _tenant_context_from_bearer_token(
    authorization: str,
    *,
    jwt_secret: str,
    session: AsyncSession,
) -> TenantContext:
    """Resolve tenant identity from a token and current persisted user state."""
    if not authorization.startswith("Bearer "):
        raise TenantContextMissing("invalid tenant authentication")

    payload: dict[str, Any] | None = decode_access_token(
        authorization.split(" ", 1)[1], jwt_secret
    )
    if payload is None:
        raise TenantContextMissing("invalid tenant authentication")

    try:
        user_id = UUID(str(payload["sub"]))
        organization_id = UUID(str(payload["org_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise TenantContextMissing("invalid tenant authentication") from exc

    token_version = payload.get("tv")
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or user.organization_id != organization_id
        or payload.get("role") != user.role
        or not isinstance(token_version, int)
        or token_version != user.token_version
    ):
        raise TenantContextMissing("invalid tenant authentication")
    return TenantContext(organization_id=organization_id)


async def require_tenant_context(
    authorization: str | None = Header(default=None),
    x_organization_id: str | None = Header(default=None, alias=_TENANT_HEADER),
    settings: Settings = Depends(get_app_settings),
    jwt_secret: str = Depends(get_jwt_secret),
    session: AsyncSession = Depends(get_db_session),
) -> TenantContext:
    """Resolve a verified JWT tenant, or a development-only header fallback."""
    if authorization:
        return await _tenant_context_from_bearer_token(
            authorization,
            jwt_secret=jwt_secret,
            session=session,
        )

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
