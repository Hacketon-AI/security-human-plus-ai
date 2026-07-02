"""Asset use cases.

Registration is gated on the owning project being visible to the tenant and
active. Targets are normalized per type. Verification can only be *requested*
here: it moves a draft asset to ``pending_verification`` and records the
requested method; the proof flow and the transition to ``verified`` belong to a
later stage and are never driven by client input.
"""

from collections.abc import Sequence
from uuid import UUID

from app.modules.assets.enums import AssetStatus
from app.modules.assets.errors import AssetNotFound, InvalidAssetStateTransition
from app.modules.assets.models import Asset
from app.modules.assets.mutation_policy import ensure_metadata_update_allowed
from app.modules.assets.repository import AssetRepository
from app.modules.assets.schemas import (
    AssetCreate,
    AssetUpdate,
    AssetVerificationRequest,
)
from app.modules.assets.target import normalize_target
from app.modules.projects.enums import ProjectStatus
from app.modules.projects.errors import ProjectNotAcceptingAssets, ProjectNotFound
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from app.platform.clock import Clock

_NOT_FOUND = "asset not found"
_PROJECT_NOT_FOUND = "project not found"


class AssetService:
    """Registers, reads, edits, and requests verification for assets."""

    def __init__(
        self,
        assets: AssetRepository,
        projects: ProjectRepository,
        clock: Clock,
    ) -> None:
        self._assets = assets
        self._projects = projects
        self._clock = clock

    async def register(self, tenant: TenantContext, payload: AssetCreate) -> Asset:
        # Resolving the project within the tenant doubles as the cross-tenant
        # gate: another tenant's project is simply not found.
        project = await self._projects.get_in_org(
            payload.project_id, tenant.organization_id
        )
        if project is None:
            raise ProjectNotFound(_PROJECT_NOT_FOUND)
        if project.status is not ProjectStatus.active:
            raise ProjectNotAcceptingAssets(
                f"project status {project.status.value} cannot accept new assets"
            )

        target = normalize_target(payload.asset_type, payload.target)
        asset = Asset(
            organization_id=tenant.organization_id,
            project_id=project.id,
            name=payload.name.strip(),
            asset_type=payload.asset_type,
            environment=payload.environment,
            target=target,
            criticality=payload.criticality,
            status=AssetStatus.draft,
        )
        await self._assets.add(asset)
        return asset

    async def list_for_tenant(
        self, tenant: TenantContext, project_id: UUID | None
    ) -> Sequence[Asset]:
        return await self._assets.list_for_org(tenant.organization_id, project_id)

    async def get_for_tenant(self, asset_id: UUID, tenant: TenantContext) -> Asset:
        asset = await self._assets.get_in_org(asset_id, tenant.organization_id)
        if asset is None:
            raise AssetNotFound(_NOT_FOUND)
        return asset

    async def update(
        self, asset_id: UUID, tenant: TenantContext, payload: AssetUpdate
    ) -> Asset:
        asset = await self.get_for_tenant(asset_id, tenant)
        changes = payload.model_dump(exclude_unset=True)
        # The mutation policy is the single authority on what may change per
        # state; suspended/retired assets are protected here, not in the route.
        ensure_metadata_update_allowed(asset.status, changes.keys())
        if "name" in changes and payload.name is not None:
            asset.name = payload.name.strip()
        if "criticality" in changes and payload.criticality is not None:
            asset.criticality = payload.criticality
        await self._assets.persist(asset)
        return asset

    async def request_verification(
        self,
        asset_id: UUID,
        tenant: TenantContext,
        payload: AssetVerificationRequest,
    ) -> Asset:
        asset = await self.get_for_tenant(asset_id, tenant)
        if asset.status is not AssetStatus.draft:
            raise InvalidAssetStateTransition(
                "verification can only be requested for a draft asset; "
                f"current status is {asset.status.value}"
            )
        asset.status = AssetStatus.pending_verification
        asset.verification_method = payload.method
        asset.verification_requested_at = self._clock.now()
        await self._assets.persist(asset)
        return asset
