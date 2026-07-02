"""Data access for asset verification challenges. Concrete and specific."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.asset_verifications.enums import ChallengeStatus
from app.modules.asset_verifications.models import AssetVerificationChallenge


class AssetVerificationChallengeRepository:
    """Reads and writes :class:`AssetVerificationChallenge` rows on one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, challenge: AssetVerificationChallenge) -> None:
        """Persist a new challenge and load server-set columns."""
        self._session.add(challenge)
        await self._session.flush()
        await self._session.refresh(challenge)

    async def persist(self, challenge: AssetVerificationChallenge) -> None:
        """Flush in-place mutations and reload server-set columns."""
        await self._session.flush()
        await self._session.refresh(challenge)

    async def get_in_org(
        self, challenge_id: UUID, asset_id: UUID, organization_id: UUID
    ) -> AssetVerificationChallenge | None:
        result = await self._session.execute(
            select(AssetVerificationChallenge).where(
                AssetVerificationChallenge.id == challenge_id,
                AssetVerificationChallenge.asset_id == asset_id,
                AssetVerificationChallenge.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_update(
        self, challenge_id: UUID, asset_id: UUID, organization_id: UUID
    ) -> AssetVerificationChallenge | None:
        """Tenant-scoped fetch that locks the challenge row for the transaction."""
        result = await self._session.execute(
            select(AssetVerificationChallenge)
            .where(
                AssetVerificationChallenge.id == challenge_id,
                AssetVerificationChallenge.asset_id == asset_id,
                AssetVerificationChallenge.organization_id == organization_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_current_for_asset(
        self, asset_id: UUID, organization_id: UUID
    ) -> AssetVerificationChallenge | None:
        """The most recently created challenge for the asset, if any."""
        result = await self._session.execute(
            select(AssetVerificationChallenge)
            .where(
                AssetVerificationChallenge.asset_id == asset_id,
                AssetVerificationChallenge.organization_id == organization_id,
            )
            .order_by(AssetVerificationChallenge.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def pending_exists_for_asset(
        self, asset_id: UUID, organization_id: UUID
    ) -> bool:
        """Return True when a pending challenge already exists for the asset.

        Called under the asset row lock during create so the pre-check is
        serialized; the partial unique index remains the database-level backstop.
        """
        result = await self._session.execute(
            select(AssetVerificationChallenge.id)
            .where(
                AssetVerificationChallenge.asset_id == asset_id,
                AssetVerificationChallenge.organization_id == organization_id,
                AssetVerificationChallenge.status == ChallengeStatus.pending,
            )
            .limit(1)
        )
        return result.first() is not None
