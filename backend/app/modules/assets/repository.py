"""Data access for assets. Concrete and tenant-scoped; no generic base."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.models import Asset


class AssetRepository:
    """Reads and writes :class:`Asset` rows on one session.

    Every read is scoped by ``organization_id`` so an asset is never returned
    to a tenant that does not own it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, asset: Asset) -> None:
        self._session.add(asset)
        await self._session.flush()
        await self._session.refresh(asset)

    async def persist(self, asset: Asset) -> None:
        """Flush pending mutations and reload server-managed columns."""
        await self._session.flush()
        await self._session.refresh(asset)

    async def get_in_org(self, asset_id: UUID, organization_id: UUID) -> Asset | None:
        result = await self._session.execute(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_in_org_for_update(
        self, asset_id: UUID, organization_id: UUID
    ) -> Asset | None:
        """Tenant-scoped fetch that locks the asset row (``SELECT … FOR UPDATE``).

        Used by ownership verification to serialize concurrent challenge creates
        and verifies against the same asset.
        """
        result = await self._session.execute(
            select(Asset)
            .where(
                Asset.id == asset_id,
                Asset.organization_id == organization_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self, organization_id: UUID, project_id: UUID | None
    ) -> Sequence[Asset]:
        statement = select(Asset).where(Asset.organization_id == organization_id)
        if project_id is not None:
            statement = statement.where(Asset.project_id == project_id)
        result = await self._session.execute(statement.order_by(Asset.created_at))
        return result.scalars().all()
