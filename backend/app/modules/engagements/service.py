"""Engagement use cases.

Holds the domain logic kept out of routers, Pydantic validators, and ORM
models: state transitions, scope validation, authorization dependency checks,
kill switch management, and concurrent-safety via conditional updates.
"""

import re
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from app.modules.assets.enums import AssetStatus
from app.modules.assets.errors import AssetNotFound
from app.modules.assets.repository import AssetRepository
from app.modules.authorizations.enums import AuthorizationStatus, RiskTier
from app.modules.authorizations.errors import AuthorizationNotFound as AuthNotFound
from app.modules.authorizations.models import AuthorizationScope
from app.modules.authorizations.repository import AuthorizationRepository
from app.modules.engagements.enums import EngagementStatus
from app.modules.engagements.errors import (
    AuthorizationNotValidForEngagement,
    EngagementActivationBlocked,
    EngagementImmutableError,
    EngagementNotFound,
    InvalidEngagementScope,
    InvalidEngagementStateTransition,
    InvalidEngagementTimeRange,
    KillSwitchImmutableError,
)
from app.modules.engagements.models import Engagement, EngagementScope
from app.modules.engagements.repository import EngagementRepository
from app.modules.engagements.schemas import (
    EngagementCreate,
    EngagementScopeCreate,
    EngagementUpdate,
    KillSwitchRequest,
)
from app.modules.organizations.enums import OrganizationStatus
from app.modules.organizations.errors import OrganizationNotAcceptingProjects
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.enums import ProjectStatus
from app.modules.projects.errors import ProjectNotAcceptingAssets, ProjectNotFound
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from app.platform.clock import Clock

_MAX_DURATION_DAYS = 30
_MAX_DURATION = timedelta(days=_MAX_DURATION_DAYS)

_NOT_FOUND = "engagement not found"
_PROJECT_NOT_FOUND = "project not found"

# Allowed state transitions. No other transition is permitted.
_TRANSITIONS: dict[EngagementStatus, frozenset[EngagementStatus]] = {
    EngagementStatus.draft: frozenset(
        {EngagementStatus.scheduled, EngagementStatus.cancelled}
    ),
    EngagementStatus.scheduled: frozenset(
        {EngagementStatus.active, EngagementStatus.cancelled}
    ),
    EngagementStatus.active: frozenset(
        {EngagementStatus.paused, EngagementStatus.completed}
    ),
    EngagementStatus.paused: frozenset(
        {EngagementStatus.active, EngagementStatus.cancelled}
    ),
}

# Engagement statuses where the kill switch may be toggled.
_KILL_SWITCH_ELIGIBLE: frozenset[EngagementStatus] = frozenset(
    {
        EngagementStatus.scheduled,
        EngagementStatus.active,
        EngagementStatus.paused,
    }
)

# Terminal statuses — no mutations allowed.
_TERMINAL: frozenset[EngagementStatus] = frozenset(
    {EngagementStatus.completed, EngagementStatus.cancelled}
)

# Scalar fields editable via PATCH on a draft engagement.
_UPDATABLE_SCALAR_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "starts_at",
        "ends_at",
        "timezone",
        "max_risk_tier",
        "default_rate_limit_per_minute",
        "default_concurrency_limit",
        "emergency_contact_name",
        "emergency_contact_email",
        "emergency_contact_phone",
    }
)

# Lowercase hex SHA-256 digest: exactly 64 hex characters.
_SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")


class EngagementService:
    """Creates, reads, mutates, and transitions engagements."""

    def __init__(
        self,
        engagements: EngagementRepository,
        authorizations: AuthorizationRepository,
        assets: AssetRepository,
        projects: ProjectRepository,
        organizations: OrganizationRepository,
        clock: Clock,
    ) -> None:
        self._engagements = engagements
        self._authorizations = authorizations
        self._assets = assets
        self._projects = projects
        self._organizations = organizations
        self._clock = clock

    # ------------------------------------------------------------------
    # Create / Read / Update
    # ------------------------------------------------------------------

    async def create(
        self,
        tenant: TenantContext,
        project_id: UUID,
        payload: EngagementCreate,
    ) -> Engagement:
        project = await self._projects.get_in_org(project_id, tenant.organization_id)
        if project is None:
            raise ProjectNotFound(_PROJECT_NOT_FOUND)
        if project.status is not ProjectStatus.active:
            raise ProjectNotAcceptingAssets(
                f"project status {project.status.value} cannot accept engagements"
            )

        organization = await self._organizations.get(tenant.organization_id)
        if organization is None or organization.status is not OrganizationStatus.active:
            raise OrganizationNotAcceptingProjects("organization is not active")

        # Validate the linked authorization exists and is active.
        authorization = await self._authorizations.get_in_org(
            payload.authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthNotFound("authorization not found")
        if authorization.status is not AuthorizationStatus.active:
            raise AuthorizationNotValidForEngagement(
                f"authorization status {authorization.status.value} "
                "is not valid for an engagement"
            )

        self._validate_time_range(payload.starts_at, payload.ends_at)

        # Build scopes and validate against the authorization.
        scopes = await self._build_scopes(
            tenant, project_id, payload.scopes, authorization.id
        )

        engagement = Engagement(
            organization_id=tenant.organization_id,
            project_id=project_id,
            authorization_id=authorization.id,
            name=payload.name.strip(),
            description=payload.description,
            status=EngagementStatus.draft,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            timezone=payload.timezone.strip(),
            max_risk_tier=payload.max_risk_tier,
            default_rate_limit_per_minute=payload.default_rate_limit_per_minute,
            default_concurrency_limit=payload.default_concurrency_limit,
            emergency_contact_name=payload.emergency_contact_name.strip(),
            emergency_contact_email=payload.emergency_contact_email.strip(),
            emergency_contact_phone=(
                payload.emergency_contact_phone.strip()
                if payload.emergency_contact_phone
                else None
            ),
        )
        engagement.scopes = scopes
        await self._engagements.add(engagement)
        return engagement

    async def get_for_tenant(
        self, engagement_id: UUID, tenant: TenantContext
    ) -> Engagement:
        engagement = await self._engagements.get_in_org(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)
        return engagement

    async def list_for_project(
        self, project_id: UUID, tenant: TenantContext
    ) -> Sequence[Engagement]:
        return await self._engagements.list_for_project(
            project_id, tenant.organization_id
        )

    async def update(
        self,
        engagement_id: UUID,
        tenant: TenantContext,
        payload: EngagementUpdate,
    ) -> Engagement:
        engagement = await self._engagements.get_in_org_for_update(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)
        if engagement.status in _TERMINAL:
            raise EngagementImmutableError(
                f"engagement status {engagement.status.value} does not permit updates"
            )
        if engagement.status is not EngagementStatus.draft:
            raise EngagementImmutableError(
                f"engagement status {engagement.status.value} does not permit updates"
            )

        # Dump only scalar fields; scopes are handled from the typed payload so
        # nested models are not flattened to plain dicts.
        changes = payload.model_dump(exclude_unset=True, exclude={"scopes"})

        for field, value in changes.items():
            if value is not None and field in _UPDATABLE_SCALAR_FIELDS:
                setattr(
                    engagement,
                    field,
                    value.strip() if isinstance(value, str) else value,
                )

        if "scopes" in payload.model_fields_set and payload.scopes is not None:
            scopes = await self._build_scopes(
                tenant,
                engagement.project_id,
                payload.scopes,
                engagement.authorization_id,
            )
            await self._engagements.replace_scopes(engagement, scopes)

        self._validate_time_range(engagement.starts_at, engagement.ends_at)

        await self._engagements.persist(engagement)
        return engagement

    # ------------------------------------------------------------------
    # State Transitions
    # ------------------------------------------------------------------

    async def schedule(self, engagement_id: UUID, tenant: TenantContext) -> Engagement:
        engagement = await self._engagements.get_in_org_for_update(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)

        self._ensure_transition_allowed(engagement.status, EngagementStatus.scheduled)

        await self._validate_authorization_for_operation(engagement, tenant)
        self._validate_time_range(engagement.starts_at, engagement.ends_at)
        await self._validate_scopes_for_operation(engagement, tenant)

        success = await self._engagements.conditional_transition(
            engagement_id,
            tenant.organization_id,
            expected_status=EngagementStatus.draft,
            new_status=EngagementStatus.scheduled,
        )
        if not success:
            raise InvalidEngagementStateTransition(
                "engagement was modified concurrently; cannot schedule"
            )
        await self._engagements.persist(engagement)
        return engagement

    async def activate(self, engagement_id: UUID, tenant: TenantContext) -> Engagement:
        engagement = await self._engagements.get_in_org_for_update(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)

        if engagement.status is not EngagementStatus.scheduled:
            raise InvalidEngagementStateTransition(
                f"cannot activate engagement in status {engagement.status.value}"
            )

        await self._validate_authorization_for_operation(engagement, tenant)
        self._validate_time_range(engagement.starts_at, engagement.ends_at)
        await self._validate_scopes_for_operation(engagement, tenant)

        now = self._clock.now()
        if now < engagement.starts_at:
            raise EngagementActivationBlocked(
                "activation is not permitted before starts_at"
            )
        if now >= engagement.ends_at:
            raise EngagementActivationBlocked(
                "activation is not permitted after ends_at"
            )

        success = await self._engagements.conditional_transition(
            engagement_id,
            tenant.organization_id,
            expected_status=EngagementStatus.scheduled,
            new_status=EngagementStatus.active,
            activated_at=now,
        )
        if not success:
            raise InvalidEngagementStateTransition(
                "engagement was modified concurrently; cannot activate"
            )
        await self._engagements.persist(engagement)
        return engagement

    async def pause(self, engagement_id: UUID, tenant: TenantContext) -> Engagement:
        engagement = await self._engagements.get_in_org_for_update(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)

        self._ensure_transition_allowed(engagement.status, EngagementStatus.paused)

        now = self._clock.now()
        success = await self._engagements.conditional_transition(
            engagement_id,
            tenant.organization_id,
            expected_status=EngagementStatus.active,
            new_status=EngagementStatus.paused,
            paused_at=now,
        )
        if not success:
            raise InvalidEngagementStateTransition(
                "engagement was modified concurrently; cannot pause"
            )
        await self._engagements.persist(engagement)
        return engagement

    async def resume(self, engagement_id: UUID, tenant: TenantContext) -> Engagement:
        engagement = await self._engagements.get_in_org_for_update(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)

        self._ensure_transition_allowed(engagement.status, EngagementStatus.active)

        success = await self._engagements.conditional_transition(
            engagement_id,
            tenant.organization_id,
            expected_status=EngagementStatus.paused,
            new_status=EngagementStatus.active,
        )
        if not success:
            raise InvalidEngagementStateTransition(
                "engagement was modified concurrently; cannot resume"
            )
        await self._engagements.persist(engagement)
        return engagement

    async def complete(self, engagement_id: UUID, tenant: TenantContext) -> Engagement:
        engagement = await self._engagements.get_in_org_for_update(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)

        self._ensure_transition_allowed(engagement.status, EngagementStatus.completed)

        now = self._clock.now()
        success = await self._engagements.conditional_transition(
            engagement_id,
            tenant.organization_id,
            expected_status=EngagementStatus.active,
            new_status=EngagementStatus.completed,
            completed_at=now,
        )
        if not success:
            raise InvalidEngagementStateTransition(
                "engagement was modified concurrently; cannot complete"
            )
        await self._engagements.persist(engagement)
        return engagement

    async def cancel(self, engagement_id: UUID, tenant: TenantContext) -> Engagement:
        engagement = await self._engagements.get_in_org_for_update(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)

        self._ensure_transition_allowed(engagement.status, EngagementStatus.cancelled)

        now = self._clock.now()
        current = engagement.status
        success = await self._engagements.conditional_transition(
            engagement_id,
            tenant.organization_id,
            expected_status=current,
            new_status=EngagementStatus.cancelled,
            cancelled_at=now,
        )
        if not success:
            raise InvalidEngagementStateTransition(
                "engagement was modified concurrently; cannot cancel"
            )
        await self._engagements.persist(engagement)
        return engagement

    # ------------------------------------------------------------------
    # Kill Switch
    # ------------------------------------------------------------------

    async def set_kill_switch(
        self,
        engagement_id: UUID,
        tenant: TenantContext,
        payload: KillSwitchRequest,
    ) -> Engagement:
        engagement = await self._engagements.get_in_org_for_update(
            engagement_id, tenant.organization_id
        )
        if engagement is None:
            raise EngagementNotFound(_NOT_FOUND)

        if engagement.status in _TERMINAL:
            raise KillSwitchImmutableError(
                f"kill switch cannot be modified for a {engagement.status.value} "
                "engagement"
            )

        engagement.kill_switch_active = payload.active
        engagement.kill_switch_reason = (
            payload.reason.strip() if payload.active else None
        )

        await self._engagements.persist(engagement)
        return engagement

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_transition_allowed(
        current: EngagementStatus, target: EngagementStatus
    ) -> None:
        allowed = _TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise InvalidEngagementStateTransition(
                f"transition from {current.value} to {target.value} is not allowed"
            )

    @staticmethod
    def _validate_time_range(starts_at: object, ends_at: object) -> None:
        from datetime import datetime as dt

        if not isinstance(starts_at, dt) or not isinstance(ends_at, dt):
            raise InvalidEngagementTimeRange(
                "starts_at and ends_at must be datetime values"
            )
        if ends_at <= starts_at:
            raise InvalidEngagementTimeRange("ends_at must be after starts_at")
        if ends_at - starts_at > _MAX_DURATION:
            raise InvalidEngagementTimeRange(
                f"engagement duration exceeds the maximum of {_MAX_DURATION_DAYS} days"
            )

    async def _validate_authorization_for_operation(
        self, engagement: Engagement, tenant: TenantContext
    ) -> None:
        """Ensure the linked authorization is still active and covers the
        engagement window and risk tier."""
        authorization = await self._authorizations.get_in_org(
            engagement.authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotValidForEngagement(
                "linked authorization no longer exists"
            )
        if authorization.status is not AuthorizationStatus.active:
            raise AuthorizationNotValidForEngagement(
                f"linked authorization status {authorization.status.value} "
                "is not active"
            )

        now = self._clock.now()
        if now < authorization.valid_from or now >= authorization.valid_until:
            raise AuthorizationNotValidForEngagement(
                "linked authorization is not within its valid time window"
            )

        # Engagement window must be inside authorization window.
        if engagement.starts_at < authorization.valid_from:
            raise AuthorizationNotValidForEngagement(
                "engagement starts_at is before authorization valid_from"
            )
        if engagement.ends_at > authorization.valid_until:
            raise AuthorizationNotValidForEngagement(
                "engagement ends_at is after authorization valid_until"
            )

        # Risk tier must not exceed the authorization's maximum.
        if not _risk_tier_lte(
            engagement.max_risk_tier, authorization.maximum_risk_tier
        ):
            raise AuthorizationNotValidForEngagement(
                f"engagement max_risk_tier {engagement.max_risk_tier.value} "
                f"exceeds authorization maximum "
                f"{authorization.maximum_risk_tier.value}"
            )

    async def _validate_scopes_for_operation(
        self, engagement: Engagement, tenant: TenantContext
    ) -> None:
        """Validate every scope asset and ensure it falls within the
        authorization scopes."""
        if not engagement.scopes:
            raise InvalidEngagementScope("engagement must have at least one scope")

        # Collect authorization scope asset IDs for the containment check.
        authorization = await self._authorizations.get_in_org(
            engagement.authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotValidForEngagement(
                "linked authorization no longer exists"
            )
        auth_scope_asset_ids: set[UUID] = {s.asset_id for s in authorization.scopes}

        for scope in engagement.scopes:
            asset = await self._assets.get_in_org(
                scope.asset_id, tenant.organization_id
            )
            if asset is None:
                raise InvalidEngagementScope(
                    f"scope asset {scope.asset_id} no longer exists"
                )
            if asset.status is not AssetStatus.verified:
                raise InvalidEngagementScope(
                    f"scope asset {asset.id} is not verified "
                    f"(current status: {asset.status.value})"
                )
            if asset.project_id != engagement.project_id:
                raise InvalidEngagementScope(
                    f"scope asset {asset.id} does not belong to "
                    f"project {engagement.project_id}"
                )
            if asset.id not in auth_scope_asset_ids:
                raise InvalidEngagementScope(
                    f"asset {asset.id} is not within the linked authorization scopes"
                )

    async def _build_scopes(
        self,
        tenant: TenantContext,
        project_id: UUID,
        payloads: list[EngagementScopeCreate],
        authorization_id: UUID,
    ) -> list[EngagementScope]:
        # Load the linked authorization once (tenant-scoped fetch guarantees the
        # organization match) so any supplied authorization_scope_id can be
        # validated against its scopes. selectin eagerly loads the scopes.
        authorization_scopes_by_id = await self._authorization_scopes_by_id(
            authorization_id, tenant
        )

        scopes: list[EngagementScope] = []
        for p in payloads:
            asset = await self._assets.get_in_org(p.asset_id, tenant.organization_id)
            if asset is None:
                raise AssetNotFound("asset not found")
            if asset.project_id != project_id:
                raise InvalidEngagementScope(
                    f"asset {asset.id} does not belong to project {project_id}"
                )
            if asset.status is not AssetStatus.verified:
                raise InvalidEngagementScope(
                    f"asset {asset.id} is not verified; "
                    f"current status is {asset.status.value}"
                )
            if p.authorization_scope_id is not None:
                # The supplied authorization scope must belong to the linked
                # authorization (and thus this tenant) and cover this asset.
                authorization_scope = authorization_scopes_by_id.get(
                    p.authorization_scope_id
                )
                if authorization_scope is None:
                    raise InvalidEngagementScope(
                        f"authorization_scope {p.authorization_scope_id} does not "
                        "belong to the linked authorization"
                    )
                if authorization_scope.asset_id != asset.id:
                    raise InvalidEngagementScope(
                        f"authorization_scope {p.authorization_scope_id} does not "
                        f"cover asset {asset.id}"
                    )
            scopes.append(
                EngagementScope(
                    organization_id=tenant.organization_id,
                    asset_id=asset.id,
                    authorization_scope_id=p.authorization_scope_id,
                    allowed_paths=p.allowed_paths,
                    excluded_paths=p.excluded_paths,
                    allowed_ports=p.allowed_ports,
                    rate_limit_per_minute=p.rate_limit_per_minute,
                    concurrency_limit=p.concurrency_limit,
                    notes=p.notes,
                )
            )
        return scopes

    async def _authorization_scopes_by_id(
        self, authorization_id: UUID, tenant: TenantContext
    ) -> dict[UUID, AuthorizationScope]:
        """Return the linked authorization's scopes keyed by id.

        The authorization is fetched tenant-scoped, so a scope found here is
        guaranteed to belong to both this authorization and this organization.
        """
        authorization = await self._authorizations.get_in_org(
            authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotValidForEngagement(
                "linked authorization no longer exists"
            )
        return {scope.id: scope for scope in authorization.scopes}


def _risk_tier_lte(a: RiskTier, b: RiskTier) -> bool:
    """Return True when risk tier ``a`` does not exceed ``b``."""
    _ORDER = {
        RiskTier.tier_0_passive: 0,
        RiskTier.tier_1_safe: 1,
        RiskTier.tier_2_controlled: 2,
        RiskTier.tier_3_critical: 3,
    }
    return _ORDER.get(a, -1) <= _ORDER.get(b, -1)
