"""Asset ownership verification use cases (DNS TXT).

Holds the verification domain logic kept out of routers, ORM models, Pydantic
validators, and the DNS adapter: challenge issuance, the proof comparison, and
the explicit challenge/asset state transitions. Concurrency is handled with
row locks (asset row first, then challenge row) so concurrent creates cannot
produce two pending challenges and concurrent verifies cannot double-transition.
"""

import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.modules.asset_verifications.challenge_token import (
    build_control_record_name,
    build_record_name,
    build_record_value,
    digest_value,
    generate_token,
    matches_digest,
    token_last_four,
)
from app.modules.asset_verifications.dns_resolver import (
    DnsResolutionUnavailable,
    DnsTxtResolver,
)
from app.modules.asset_verifications.enums import ChallengeMethod, ChallengeStatus
from app.modules.asset_verifications.errors import (
    ActiveChallengeConflict,
    AssetNotPendingVerification,
    InactiveVerificationTarget,
    UnsupportedVerificationAssetType,
    VerificationChallengeNotActive,
    VerificationChallengeNotFound,
)
from app.modules.asset_verifications.models import AssetVerificationChallenge
from app.modules.asset_verifications.repository import (
    AssetVerificationChallengeRepository,
)
from app.modules.assets.enums import AssetStatus, AssetType
from app.modules.assets.errors import AssetNotFound
from app.modules.assets.models import Asset
from app.modules.assets.repository import AssetRepository
from app.modules.assets.target import hostname_from_target
from app.modules.organizations.enums import OrganizationStatus
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.enums import ProjectStatus
from app.modules.projects.repository import ProjectRepository
from app.modules.shared.persistence import unique_violation_constraint
from app.modules.tenancy.context import TenantContext
from app.platform.clock import Clock

# Asset types that support DNS TXT ownership proof in this stage.
_SUPPORTED_ASSET_TYPES = frozenset({AssetType.web_application, AssetType.api})

_CHALLENGE_TTL = timedelta(hours=24)
_MAXIMUM_ATTEMPTS = 5
_DNS_TIMEOUT_SECONDS = 5.0
_PENDING_CONSTRAINT = "uq_one_pending_challenge_per_asset"

_ASSET_NOT_FOUND = "asset not found"

_MSG_VERIFIED = "ownership verified"
_MSG_ALREADY_VERIFIED = "ownership already verified"
_MSG_MISMATCH = "verification record not found or did not match"
_MSG_FAILED = "verification failed after the maximum number of attempts"
_MSG_INCONCLUSIVE = "verification could not be completed; please retry"
_MSG_EXPIRED = "verification challenge has expired; create a new challenge"


@dataclass(frozen=True, slots=True)
class ChallengeCreated:
    """A freshly issued challenge plus the one-time TXT value to publish."""

    challenge: AssetVerificationChallenge
    record_value: str


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Outcome of a verify attempt, with the affected challenge and asset."""

    challenge: AssetVerificationChallenge
    asset: Asset
    message: str


class AssetVerificationService:
    """Issues, verifies, reads, and cancels DNS TXT ownership challenges."""

    def __init__(
        self,
        challenges: AssetVerificationChallengeRepository,
        assets: AssetRepository,
        projects: ProjectRepository,
        organizations: OrganizationRepository,
        resolver: DnsTxtResolver,
        clock: Clock,
    ) -> None:
        self._challenges = challenges
        self._assets = assets
        self._projects = projects
        self._organizations = organizations
        self._resolver = resolver
        self._clock = clock

    async def create_challenge(
        self, asset_id: UUID, tenant: TenantContext
    ) -> ChallengeCreated:
        # Lock the asset row to serialize concurrent creates for this asset.
        asset = await self._assets.get_in_org_for_update(
            asset_id, tenant.organization_id
        )
        if asset is None:
            raise AssetNotFound(_ASSET_NOT_FOUND)
        if asset.asset_type not in _SUPPORTED_ASSET_TYPES:
            raise UnsupportedVerificationAssetType(
                f"asset type {asset.asset_type.value} does not support DNS TXT "
                "verification"
            )
        if asset.status is not AssetStatus.pending_verification:
            raise AssetNotPendingVerification(
                f"asset status {asset.status.value} cannot start verification"
            )
        await self._ensure_target_active(asset, tenant)

        # Reject when a pending challenge already exists for this asset.
        # The check runs under the asset row lock so concurrent creates are
        # serialized; the partial unique index is the database-level backstop.
        if await self._challenges.pending_exists_for_asset(
            asset_id, tenant.organization_id
        ):
            raise ActiveChallengeConflict(
                "a pending verification challenge already exists for this asset"
            )

        hostname = hostname_from_target(asset.target)
        token = generate_token()
        record_value = build_record_value(token)
        now = self._clock.now()
        challenge = AssetVerificationChallenge(
            organization_id=tenant.organization_id,
            project_id=asset.project_id,
            asset_id=asset_id,
            method=ChallengeMethod.dns_txt,
            status=ChallengeStatus.pending,
            record_name=build_record_name(hostname),
            token_digest=digest_value(record_value),
            token_last_four=token_last_four(token),
            attempts=0,
            maximum_attempts=_MAXIMUM_ATTEMPTS,
            expires_at=now + _CHALLENGE_TTL,
        )
        try:
            await self._challenges.add(challenge)
        except IntegrityError as exc:
            # Backstop for the partial unique index if a create ever races past
            # the asset row lock.
            if unique_violation_constraint(exc) == _PENDING_CONSTRAINT:
                raise ActiveChallengeConflict(
                    "a pending verification challenge already exists for this asset"
                ) from exc
            raise
        return ChallengeCreated(challenge=challenge, record_value=record_value)

    async def get_current(
        self, asset_id: UUID, tenant: TenantContext
    ) -> AssetVerificationChallenge:
        challenge = await self._challenges.get_current_for_asset(
            asset_id, tenant.organization_id
        )
        if challenge is None:
            raise VerificationChallengeNotFound("no verification challenge found")
        return challenge

    async def verify(
        self, asset_id: UUID, challenge_id: UUID, tenant: TenantContext
    ) -> VerificationResult:
        # Lock asset first, then challenge — a consistent order with create() to
        # avoid deadlocks.
        asset = await self._assets.get_in_org_for_update(
            asset_id, tenant.organization_id
        )
        if asset is None:
            raise AssetNotFound(_ASSET_NOT_FOUND)
        challenge = await self._challenges.get_for_update(
            challenge_id, asset_id, tenant.organization_id
        )
        if challenge is None:
            raise VerificationChallengeNotFound("verification challenge not found")

        if challenge.status is ChallengeStatus.verified:
            return VerificationResult(challenge, asset, _MSG_ALREADY_VERIFIED)
        if challenge.status is ChallengeStatus.expired:
            return VerificationResult(challenge, asset, _MSG_EXPIRED)
        if challenge.status in (ChallengeStatus.failed, ChallengeStatus.cancelled):
            raise VerificationChallengeNotActive(
                f"challenge status {challenge.status.value} cannot be verified"
            )

        now = self._clock.now()
        if now >= challenge.expires_at:
            challenge.status = ChallengeStatus.expired
            challenge.failure_reason = "challenge expired"
            await self._challenges.persist(challenge)
            return VerificationResult(challenge, asset, _MSG_EXPIRED)

        if asset.status is not AssetStatus.pending_verification:
            raise AssetNotPendingVerification(
                f"asset status {asset.status.value} cannot be verified"
            )

        try:
            values = await self._resolver.resolve_txt(
                challenge.record_name, _DNS_TIMEOUT_SECONDS
            )
        except DnsResolutionUnavailable:
            # Transient failure: inconclusive, no state change, no attempt spent.
            return VerificationResult(challenge, asset, _MSG_INCONCLUSIVE)

        matched = any(matches_digest(value, challenge.token_digest) for value in values)
        if matched:
            hostname = hostname_from_target(asset.target)
            if await self._is_wildcard(hostname, challenge.token_digest):
                # A zone wildcard answering the verification name is not proof.
                matched = False

        if matched:
            challenge.status = ChallengeStatus.verified
            challenge.verified_at = now
            asset.status = AssetStatus.verified
            asset.ownership_verified_at = now
            await self._challenges.persist(challenge)
            await self._assets.persist(asset)
            return VerificationResult(challenge, asset, _MSG_VERIFIED)

        challenge.attempts += 1
        challenge.last_attempted_at = now
        message = _MSG_MISMATCH
        if challenge.attempts >= challenge.maximum_attempts:
            challenge.status = ChallengeStatus.failed
            challenge.failure_reason = "maximum attempts reached"
            message = _MSG_FAILED
        await self._challenges.persist(challenge)
        return VerificationResult(challenge, asset, message)

    async def cancel(
        self, asset_id: UUID, challenge_id: UUID, tenant: TenantContext
    ) -> AssetVerificationChallenge:
        challenge = await self._challenges.get_for_update(
            challenge_id, asset_id, tenant.organization_id
        )
        if challenge is None:
            raise VerificationChallengeNotFound("verification challenge not found")
        if challenge.status is ChallengeStatus.cancelled:
            return challenge
        if challenge.status is not ChallengeStatus.pending:
            raise VerificationChallengeNotActive(
                f"challenge status {challenge.status.value} cannot be cancelled"
            )
        challenge.status = ChallengeStatus.cancelled
        await self._challenges.persist(challenge)
        return challenge

    async def _ensure_target_active(self, asset: Asset, tenant: TenantContext) -> None:
        project = await self._projects.get_in_org(
            asset.project_id, tenant.organization_id
        )
        if project is None or project.status is not ProjectStatus.active:
            raise InactiveVerificationTarget("owning project is not active")
        organization = await self._organizations.get(tenant.organization_id)
        if organization is None or organization.status is not OrganizationStatus.active:
            raise InactiveVerificationTarget("owning organization is not active")

    async def _is_wildcard(self, hostname: str, expected_digest: str) -> bool:
        """Detect a zone wildcard that would answer the verification name.

        Probes a random sibling record at the same label depth. Only a wildcard
        echoing the exact secret value would match the digest, so this rarely
        triggers — the 256-bit token is the primary defense — but it ensures a
        wildcard response is never accepted as proof.
        """
        control_name = build_control_record_name(hostname, secrets.token_hex(8))
        try:
            values = await self._resolver.resolve_txt(
                control_name, _DNS_TIMEOUT_SECONDS
            )
        except DnsResolutionUnavailable:
            return False
        return any(matches_digest(value, expected_digest) for value in values)
