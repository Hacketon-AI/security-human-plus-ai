"""HTTP routes for asset ownership verification. Thin: parse, authorize, map.

The create/verify/cancel endpoints accept no request body — token, record name,
and expiry are server-derived — so a client cannot influence the DNS record or
the expected proof.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.asset_verifications.challenge_token import RECORD_TYPE
from app.modules.asset_verifications.dns_resolver import (
    DnsTxtResolver,
    get_dns_txt_resolver,
)
from app.modules.asset_verifications.repository import (
    AssetVerificationChallengeRepository,
)
from app.modules.asset_verifications.schemas import (
    VerificationChallengeCancelledResponse,
    VerificationChallengeCreatedResponse,
    VerificationChallengeResponse,
    VerificationResultResponse,
)
from app.modules.asset_verifications.service import AssetVerificationService
from app.modules.assets.repository import AssetRepository
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from app.modules.tenancy.development_auth import require_tenant_context
from app.platform.clock import Clock, get_clock
from app.platform.dependencies import get_session

router = APIRouter(
    prefix="/api/v1/assets/{asset_id}/verification-challenges",
    tags=["asset-verifications"],
)


def _service(
    session: AsyncSession = Depends(get_session),
    resolver: DnsTxtResolver = Depends(get_dns_txt_resolver),
    clock: Clock = Depends(get_clock),
) -> AssetVerificationService:
    return AssetVerificationService(
        AssetVerificationChallengeRepository(session),
        AssetRepository(session),
        ProjectRepository(session),
        OrganizationRepository(session),
        resolver,
        clock,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_verification_challenge(
    asset_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetVerificationService = Depends(_service),
) -> VerificationChallengeCreatedResponse:
    created = await service.create_challenge(asset_id, tenant)
    challenge = created.challenge
    return VerificationChallengeCreatedResponse(
        challenge_id=challenge.id,
        method=challenge.method,
        record_name=challenge.record_name,
        record_type=RECORD_TYPE,
        record_value=created.record_value,
        expires_at=challenge.expires_at,
        maximum_attempts=challenge.maximum_attempts,
    )


@router.get("/current")
async def get_current_verification_challenge(
    asset_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetVerificationService = Depends(_service),
) -> VerificationChallengeResponse:
    challenge = await service.get_current(asset_id, tenant)
    return VerificationChallengeResponse(
        challenge_id=challenge.id,
        method=challenge.method,
        status=challenge.status,
        record_name=challenge.record_name,
        record_type=RECORD_TYPE,
        token_last_four=challenge.token_last_four,
        attempts=challenge.attempts,
        maximum_attempts=challenge.maximum_attempts,
        expires_at=challenge.expires_at,
        verified_at=challenge.verified_at,
        last_attempted_at=challenge.last_attempted_at,
    )


@router.post("/{challenge_id}/verify")
async def verify_verification_challenge(
    asset_id: UUID,
    challenge_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetVerificationService = Depends(_service),
) -> VerificationResultResponse:
    result = await service.verify(asset_id, challenge_id, tenant)
    return VerificationResultResponse(
        challenge_id=result.challenge.id,
        challenge_status=result.challenge.status,
        asset_status=result.asset.status,
        attempts=result.challenge.attempts,
        verified_at=result.challenge.verified_at,
        message=result.message,
    )


@router.post("/{challenge_id}/cancel")
async def cancel_verification_challenge(
    asset_id: UUID,
    challenge_id: UUID,
    tenant: TenantContext = Depends(require_tenant_context),
    service: AssetVerificationService = Depends(_service),
) -> VerificationChallengeCancelledResponse:
    challenge = await service.cancel(asset_id, challenge_id, tenant)
    return VerificationChallengeCancelledResponse(
        challenge_id=challenge.id,
        challenge_status=challenge.status,
    )
