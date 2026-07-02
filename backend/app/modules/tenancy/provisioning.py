"""Organization-provisioning authorization.

Creating an organization (a tenant root) is a different concern from
authenticating within a tenant: there is no tenant yet, so the tenant header is
not used here. This adapter authorizes the provisioning action itself.

In development/test a dedicated development adapter authorizes provisioning. In
staging/production it fails closed: a production provisioning identity is not
yet configured, and this stage deliberately does not invent one (no hardcoded
admin, no default API key, no fake authentication). The temporary contract is
therefore explicitly "not production ready".
"""

from dataclasses import dataclass

from fastapi import Depends

from app.config import Settings
from app.platform.dependencies import get_app_settings
from app.platform.errors import ServiceNotConfiguredError


@dataclass(frozen=True, slots=True)
class ProvisioningContext:
    """Authorization context for a provisioning action.

    ``actor`` identifies the authorizing mechanism; in development that is the
    development adapter itself, which is sufficient to keep provisioning out of
    anonymous reach while a real identity provider is pending.
    """

    actor: str


class OrganizationProvisioningNotConfigured(ServiceNotConfiguredError):
    """No production provisioning identity is configured for this environment."""

    code = "organization_provisioning_not_configured"


async def require_provisioning(
    settings: Settings = Depends(get_app_settings),
) -> ProvisioningContext:
    """Authorize organization provisioning, or fail closed.

    Available only when the development provisioning adapter is active; refused
    in staging/production until a production provisioning identity is wired.
    """
    if not settings.development_provisioning_active:
        raise OrganizationProvisioningNotConfigured(
            "organization provisioning is not configured for this environment"
        )
    return ProvisioningContext(actor="development-provisioning")
