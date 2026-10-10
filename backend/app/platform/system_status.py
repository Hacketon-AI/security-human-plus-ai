"""Read-only runtime configuration for the console.

Reports what the running control plane is actually configured with, so the UI
never has to hardcode environment, dispatch, or AI state. Values are
non-sensitive: names and booleans only, never URLs or credentials.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.platform.dependencies import get_app_settings

router = APIRouter(tags=["system"])


class SystemStatusResponse(BaseModel):
    environment: str
    dispatcher_backend: str
    ai_router_mode: str
    claude_configured: bool
    fireworks_configured: bool


@router.get("/api/v1/system/status")
async def system_status(
    _tenant: TenantContext = Depends(require_tenant_context),
    settings: Settings = Depends(get_app_settings),
) -> SystemStatusResponse:
    return SystemStatusResponse(
        environment=settings.environment.value,
        dispatcher_backend=settings.validation_dispatcher_backend.value,
        ai_router_mode=settings.ai_router_mode,
        claude_configured=settings.anthropic_api_key is not None,
        fireworks_configured=settings.fireworks_api_key is not None,
    )
