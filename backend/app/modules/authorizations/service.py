"""Authorization use cases.

Holds the domain logic kept out of routers, Pydantic validators, and ORM
models: state transitions, scope validation, risk-tier gating, activation
guards, and concurrent-safety via conditional updates.
"""

import re
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from app.modules.assets.enums import AssetEnvironment, AssetStatus
from app.modules.assets.errors import AssetNotFound
from app.modules.assets.repository import AssetRepository
from app.modules.authorizations.enums import AuthorizationStatus, RiskTier
from app.modules.authorizations.errors import (
    AuthorizationActivationBlocked,
    AuthorizationImmutableError,
    AuthorizationNotFound,
    InvalidAuthorizationScope,
    InvalidAuthorizationStateTransition,
    InvalidAuthorizationTimeRange,
)
from app.modules.authorizations.models import Authorization, AuthorizationScope
from app.modules.authorizations.provisioning import ActivationProvisioningContext
from app.modules.authorizations.repository import AuthorizationRepository
from app.modules.authorizations.schemas import (
    AuthorizationCreate,
    AuthorizationReject,
    AuthorizationRevoke,
    AuthorizationScopeCreate,
    AuthorizationUpdate,
)
from app.modules.organizations.enums import OrganizationStatus
from app.modules.organizations.errors import OrganizationNotAcceptingProjects
from app.modules.organizations.repository import OrganizationRepository
from app.modules.projects.enums import ProjectStatus
from app.modules.projects.errors import ProjectNotAcceptingAssets, ProjectNotFound
from app.modules.projects.repository import ProjectRepository
from app.modules.tenancy.context import TenantContext
from app.platform.clock import Clock

_MAX_VALIDITY_DAYS = 90
_MAX_VALIDITY = timedelta(days=_MAX_VALIDITY_DAYS)

_NOT_FOUND = "authorization not found"
_PROJECT_NOT_FOUND = "project not found"

# Allowed state transitions. No other transition is permitted.
_TRANSITIONS: dict[AuthorizationStatus, frozenset[AuthorizationStatus]] = {
    AuthorizationStatus.draft: frozenset({AuthorizationStatus.submitted}),
    AuthorizationStatus.submitted: frozenset(
        {AuthorizationStatus.active, AuthorizationStatus.rejected}
    ),
    AuthorizationStatus.active: frozenset(
        {AuthorizationStatus.revoked, AuthorizationStatus.expired}
    ),
}

# Risk tiers that are blocked from activation until the approval engine exists.
_BLOCKED_RISK_TIERS: frozenset[RiskTier] = frozenset(
    {RiskTier.tier_2_controlled, RiskTier.tier_3_critical}
)

# Risk tiers permitted when production assets are in scope.
_PRODUCTION_RISK_TIERS: frozenset[RiskTier] = frozenset(
    {RiskTier.tier_0_passive, RiskTier.tier_1_safe}
)

# Lowercase hex SHA-256 digest: exactly 64 hex characters.
_SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")

# Scalar fields that may be updated via the PATCH endpoint on a draft
# authorization.  Relationship fields, identity fields, lifecycle timestamps,
# and status are never writable through the generic update path.
_UPDATABLE_SCALAR_FIELDS: frozenset[str] = frozenset(
    {
        "reference_number",
        "title",
        "description",
        "valid_from",
        "valid_until",
        "timezone",
        "maximum_risk_tier",
        "production_testing_allowed",
        "core_banking_testing_allowed",
        "emergency_contact_name",
        "emergency_contact_phone",
        "authorization_document_name",
        "authorization_document_sha256",
        "authorization_document_reference",
    }
)


class AuthorizationService:
    """Creates, reads, mutates, and transitions authorizations."""

    def __init__(
        self,
        authorizations: AuthorizationRepository,
        assets: AssetRepository,
        projects: ProjectRepository,
        organizations: OrganizationRepository,
        clock: Clock,
    ) -> None:
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
        payload: AuthorizationCreate,
    ) -> Authorization:
        project = await self._projects.get_in_org(project_id, tenant.organization_id)
        if project is None:
            raise ProjectNotFound(_PROJECT_NOT_FOUND)
        if project.status is not ProjectStatus.active:
            raise ProjectNotAcceptingAssets(
                f"project status {project.status.value} cannot accept authorizations"
            )

        organization = await self._organizations.get(tenant.organization_id)
        if organization is None or organization.status is not OrganizationStatus.active:
            raise OrganizationNotAcceptingProjects("organization is not active")

        self._validate_time_range(payload.valid_from, payload.valid_until)

        scopes = await self._build_scopes(tenant, project_id, payload.scopes)

        authorization = Authorization(
            organization_id=tenant.organization_id,
            project_id=project_id,
            reference_number=payload.reference_number.strip(),
            title=payload.title.strip(),
            description=payload.description,
            status=AuthorizationStatus.draft,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            timezone=payload.timezone.strip(),
            maximum_risk_tier=payload.maximum_risk_tier,
            production_testing_allowed=payload.production_testing_allowed,
            core_banking_testing_allowed=payload.core_banking_testing_allowed,
            emergency_contact_name=payload.emergency_contact_name.strip(),
            emergency_contact_phone=payload.emergency_contact_phone.strip(),
            authorization_document_name=payload.authorization_document_name.strip(),
            authorization_document_sha256=payload.authorization_document_sha256.strip(),
            authorization_document_reference=(
                payload.authorization_document_reference.strip()
                if payload.authorization_document_reference
                else None
            ),
        )
        authorization.scopes = scopes
        await self._authorizations.add(authorization)
        return authorization

    async def get_for_tenant(
        self, authorization_id: UUID, tenant: TenantContext
    ) -> Authorization:
        authorization = await self._authorizations.get_in_org(
            authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotFound(_NOT_FOUND)
        await self._auto_expire_if_needed(authorization)
        return authorization

    async def list_for_project(
        self, project_id: UUID, tenant: TenantContext
    ) -> Sequence[Authorization]:
        authorizations = await self._authorizations.list_for_project(
            project_id, tenant.organization_id
        )
        for auth in authorizations:
            await self._auto_expire_if_needed(auth)
        return authorizations

    async def update(
        self,
        authorization_id: UUID,
        tenant: TenantContext,
        payload: AuthorizationUpdate,
    ) -> Authorization:
        authorization = await self._authorizations.get_in_org_for_update(
            authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotFound(_NOT_FOUND)
        if authorization.status is not AuthorizationStatus.draft:
            raise AuthorizationImmutableError(
                f"authorization status {authorization.status.value} "
                "does not permit updates"
            )

        # Dump only scalar fields; scopes are handled from the typed payload so
        # nested models are not flattened to plain dicts.
        changes = payload.model_dump(exclude_unset=True, exclude={"scopes"})

        for field, value in changes.items():
            if value is not None and field in _UPDATABLE_SCALAR_FIELDS:
                setattr(
                    authorization,
                    field,
                    value.strip() if isinstance(value, str) else value,
                )

        if "scopes" in payload.model_fields_set and payload.scopes is not None:
            scopes = await self._build_scopes(
                tenant, authorization.project_id, payload.scopes
            )
            await self._authorizations.replace_scopes(authorization, scopes)

        self._validate_time_range(authorization.valid_from, authorization.valid_until)

        await self._authorizations.persist(authorization)
        return authorization

    # ------------------------------------------------------------------
    # State Transitions
    # ------------------------------------------------------------------

    async def submit(
        self, authorization_id: UUID, tenant: TenantContext
    ) -> Authorization:
        authorization = await self._authorizations.get_in_org_for_update(
            authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotFound(_NOT_FOUND)

        self._ensure_transition_allowed(
            authorization.status, AuthorizationStatus.submitted
        )

        self._validate_time_range(authorization.valid_from, authorization.valid_until)
        self._validate_risk_tier(authorization.maximum_risk_tier)
        self._validate_core_banking(authorization.core_banking_testing_allowed)
        self._validate_document_metadata(authorization)
        await self._validate_scopes_for_activation(authorization, tenant)

        now = self._clock.now()
        success = await self._authorizations.conditional_transition(
            authorization_id,
            tenant.organization_id,
            expected_status=AuthorizationStatus.draft,
            new_status=AuthorizationStatus.submitted,
            submitted_at=now,
        )
        if not success:
            raise InvalidAuthorizationStateTransition(
                "authorization was modified concurrently; cannot submit"
            )
        # Reload from the database so server-managed columns (updated_at) and
        # the new status are reflected in the returned object.
        await self._authorizations.persist(authorization)
        return authorization

    async def activate(
        self,
        authorization_id: UUID,
        tenant: TenantContext,
        provisioning: ActivationProvisioningContext,
    ) -> Authorization:
        authorization = await self._authorizations.get_in_org_for_update(
            authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotFound(_NOT_FOUND)

        if authorization.status is not AuthorizationStatus.submitted:
            raise InvalidAuthorizationStateTransition(
                f"cannot activate authorization in status {authorization.status.value}"
            )

        # Re-validate all activation gates against live data.
        self._validate_time_range(authorization.valid_from, authorization.valid_until)
        self._validate_risk_tier(authorization.maximum_risk_tier)
        self._validate_core_banking(authorization.core_banking_testing_allowed)
        self._validate_document_metadata(authorization)
        await self._validate_scopes_for_activation(authorization, tenant)

        now = self._clock.now()
        if now < authorization.valid_from:
            raise AuthorizationActivationBlocked(
                "activation is not permitted before valid_from"
            )
        if now >= authorization.valid_until:
            raise AuthorizationActivationBlocked(
                "activation is not permitted after valid_until"
            )

        success = await self._authorizations.conditional_transition(
            authorization_id,
            tenant.organization_id,
            expected_status=AuthorizationStatus.submitted,
            new_status=AuthorizationStatus.active,
            activated_at=now,
            activated_by_reference=provisioning.actor_reference,
        )
        if not success:
            raise InvalidAuthorizationStateTransition(
                "authorization was modified concurrently; cannot activate"
            )
        await self._authorizations.persist(authorization)
        return authorization

    async def reject(
        self,
        authorization_id: UUID,
        tenant: TenantContext,
        payload: AuthorizationReject,
    ) -> Authorization:
        authorization = await self._authorizations.get_in_org_for_update(
            authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotFound(_NOT_FOUND)

        self._ensure_transition_allowed(
            authorization.status, AuthorizationStatus.rejected
        )

        success = await self._authorizations.conditional_transition(
            authorization_id,
            tenant.organization_id,
            expected_status=AuthorizationStatus.submitted,
            new_status=AuthorizationStatus.rejected,
            rejection_reason=payload.reason.strip(),
        )
        if not success:
            raise InvalidAuthorizationStateTransition(
                "authorization was modified concurrently; cannot reject"
            )
        await self._authorizations.persist(authorization)
        return authorization

    async def revoke(
        self,
        authorization_id: UUID,
        tenant: TenantContext,
        payload: AuthorizationRevoke,
    ) -> Authorization:
        authorization = await self._authorizations.get_in_org_for_update(
            authorization_id, tenant.organization_id
        )
        if authorization is None:
            raise AuthorizationNotFound(_NOT_FOUND)

        if authorization.status is not AuthorizationStatus.active:
            raise InvalidAuthorizationStateTransition(
                f"cannot revoke authorization in status {authorization.status.value}"
            )

        await self._auto_expire_if_needed(authorization)
        if authorization.status is AuthorizationStatus.expired:  # type: ignore[comparison-overlap]
            raise InvalidAuthorizationStateTransition(
                "authorization has expired; cannot revoke"
            )

        now = self._clock.now()
        success = await self._authorizations.conditional_transition(
            authorization_id,
            tenant.organization_id,
            expected_status=AuthorizationStatus.active,
            new_status=AuthorizationStatus.revoked,
            revoked_at=now,
            revocation_reason=payload.reason.strip(),
        )
        if not success:
            raise InvalidAuthorizationStateTransition(
                "authorization was modified concurrently; cannot revoke"
            )
        await self._authorizations.persist(authorization)
        return authorization

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_transition_allowed(
        current: AuthorizationStatus, target: AuthorizationStatus
    ) -> None:
        allowed = _TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise InvalidAuthorizationStateTransition(
                f"transition from {current.value} to {target.value} is not allowed"
            )

    @staticmethod
    def _validate_time_range(valid_from: object, valid_until: object) -> None:
        from datetime import datetime as dt

        if not isinstance(valid_from, dt) or not isinstance(valid_until, dt):
            raise InvalidAuthorizationTimeRange(
                "valid_from and valid_until must be datetime values"
            )
        if valid_until <= valid_from:
            raise InvalidAuthorizationTimeRange("valid_until must be after valid_from")
        if valid_until - valid_from > _MAX_VALIDITY:
            raise InvalidAuthorizationTimeRange(
                f"validity period exceeds the maximum of {_MAX_VALIDITY_DAYS} days"
            )

    async def _build_scopes(
        self,
        tenant: TenantContext,
        project_id: UUID,
        payloads: list[AuthorizationScopeCreate],
    ) -> list[AuthorizationScope]:
        scopes: list[AuthorizationScope] = []
        for p in payloads:
            asset = await self._assets.get_in_org(p.asset_id, tenant.organization_id)
            if asset is None:
                raise AssetNotFound("asset not found")
            if asset.project_id != project_id:
                raise InvalidAuthorizationScope(
                    f"asset {asset.id} does not belong to project {project_id}"
                )
            if asset.status is not AssetStatus.verified:
                raise InvalidAuthorizationScope(
                    f"asset {asset.id} is not verified; "
                    f"current status is {asset.status.value}"
                )
            scopes.append(
                AuthorizationScope(
                    organization_id=tenant.organization_id,
                    asset_id=asset.id,
                    allowed_ports=p.allowed_ports,
                    allowed_paths=p.allowed_paths,
                    excluded_paths=p.excluded_paths,
                    maximum_requests_per_minute=p.maximum_requests_per_minute,
                    maximum_concurrency=p.maximum_concurrency,
                    notes=p.notes,
                )
            )
        return scopes

    async def _validate_scopes_for_activation(
        self, authorization: Authorization, tenant: TenantContext
    ) -> None:
        """Re-validate scope assets against live data at submit/activate time.

        Checks that every scope asset still exists, is verified, is not suspended
        or retired, and enforces production risk-tier restrictions.
        """
        if not authorization.scopes:
            raise InvalidAuthorizationScope(
                "authorization must have at least one scope"
            )

        has_production = False
        for scope in authorization.scopes:
            asset = await self._assets.get_in_org(
                scope.asset_id, tenant.organization_id
            )
            if asset is None:
                raise InvalidAuthorizationScope(
                    f"scope asset {scope.asset_id} no longer exists"
                )
            if asset.status is not AssetStatus.verified:
                raise InvalidAuthorizationScope(
                    f"scope asset {asset.id} is not verified "
                    f"(current status: {asset.status.value})"
                )
            if asset.status in (AssetStatus.suspended, AssetStatus.retired):
                raise InvalidAuthorizationScope(
                    f"scope asset {asset.id} is {asset.status.value}"
                )
            if asset.environment is AssetEnvironment.production:
                has_production = True

        if (
            has_production
            and authorization.maximum_risk_tier not in _PRODUCTION_RISK_TIERS
        ):
            raise AuthorizationActivationBlocked(
                f"production assets require maximum_risk_tier of "
                f"tier_0_passive or tier_1_safe at this stage; "
                f"current tier is {authorization.maximum_risk_tier.value}"
            )

    @staticmethod
    def _validate_risk_tier(tier: RiskTier) -> None:
        if tier in _BLOCKED_RISK_TIERS:
            raise AuthorizationActivationBlocked(
                f"risk tier {tier.value} cannot be activated: "
                "approval engine is not yet available"
            )

    @staticmethod
    def _validate_core_banking(allowed: bool) -> None:
        if allowed:
            raise AuthorizationActivationBlocked(
                "core_banking_testing_allowed must be false at this stage"
            )

    @staticmethod
    def _validate_document_metadata(authorization: Authorization) -> None:
        if (
            not authorization.authorization_document_name
            or not authorization.authorization_document_name.strip()
        ):
            raise AuthorizationActivationBlocked(
                "authorization document name is required for activation"
            )
        sha = (
            authorization.authorization_document_sha256.strip()
            if authorization.authorization_document_sha256
            else ""
        )
        if not _SHA256_HEX.fullmatch(sha):
            raise AuthorizationActivationBlocked(
                "authorization document SHA-256 is required for activation "
                "and must be a 64-character lowercase hex digest"
            )

    async def _auto_expire_if_needed(self, authorization: Authorization) -> None:
        """Transition an active authorization to expired if its time has passed."""
        if authorization.status is not AuthorizationStatus.active:
            return
        now = self._clock.now()
        if now >= authorization.valid_until:
            authorization.status = AuthorizationStatus.expired
            await self._authorizations.persist(authorization)
