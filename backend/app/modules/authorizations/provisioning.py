"""Authorization activation provisioning dependency.

Activation is a sensitive operation that requires a trusted identity. In
staging/production that identity comes from the approval engine (not yet
built). In development/test a dedicated adapter authorizes activation
so the rest of the authorization lifecycle can be exercised.

This module deliberately does NOT create a hardcoded approver, default API
key, or fake admin. The contract is explicit: activation is not production-
ready, and any attempt to activate in staging/production fails closed.

When the approval engine is built, this adapter is replaced with a real
identity resolution that records the approver.
"""

from dataclasses import dataclass

from fastapi import Depends

from app.config import Settings
from app.platform.dependencies import get_app_settings
from app.platform.errors import ServiceNotConfiguredError


@dataclass(frozen=True, slots=True)
class ActivationProvisioningContext:
    """Authorization context for an activation action.

    ``actor_reference`` is an opaque trusted identity reference. In
    development that is the development adapter itself; in production
    it will be resolved from the approval engine.
    """

    actor_reference: str


class ActivationProvisioningNotConfigured(ServiceNotConfiguredError):
    """Activation is not configured for this environment.

    Raised when the development activation adapter is inactive and no
    production approval engine has been wired, so activation fails closed.
    """

    code = "activation_provisioning_not_configured"


async def require_activation_provisioning(
    settings: Settings = Depends(get_app_settings),
) -> ActivationProvisioningContext:
    """Authorize activation, or fail closed.

    Available only when the development provisioning adapter is active.
    In staging/production this fails until the approval engine is wired.
    """
    if not settings.development_provisioning_active:
        raise ActivationProvisioningNotConfigured(
            "authorization activation is not configured for this environment"
        )
    return ActivationProvisioningContext(actor_reference="development-provisioning")
