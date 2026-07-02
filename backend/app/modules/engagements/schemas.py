"""Pydantic request/response models for the engagements API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.authorizations.enums import RiskTier
from app.modules.engagements.enums import EngagementStatus
from app.modules.shared.network_ports import AllowedPortList


class EngagementScopeCreate(BaseModel):
    """Scope definition for one asset within an engagement."""

    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    authorization_scope_id: UUID | None = None
    allowed_paths: list[str] | None = None
    excluded_paths: list[str] | None = None
    # None inherits the authorization scope's ports; an explicit (possibly empty)
    # list overrides it. Strict validation matches AuthorizationScopeCreate.
    allowed_ports: AllowedPortList = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    concurrency_limit: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=2000)


class EngagementCreate(BaseModel):
    """Body for creating an engagement (always starts as draft).

    ``organization_id`` and ``status`` are never accepted from the client.
    """

    model_config = ConfigDict(extra="forbid")

    authorization_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(min_length=1, max_length=50)
    max_risk_tier: RiskTier
    default_rate_limit_per_minute: int = Field(ge=1)
    default_concurrency_limit: int = Field(ge=1)
    emergency_contact_name: str = Field(min_length=1, max_length=200)
    emergency_contact_email: str = Field(min_length=1, max_length=320)
    emergency_contact_phone: str | None = Field(default=None, max_length=50)
    scopes: list[EngagementScopeCreate] = Field(min_length=1)


class EngagementUpdate(BaseModel):
    """Body for updating a draft engagement. All fields are optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=50)
    max_risk_tier: RiskTier | None = None
    default_rate_limit_per_minute: int | None = Field(default=None, ge=1)
    default_concurrency_limit: int | None = Field(default=None, ge=1)
    emergency_contact_name: str | None = Field(
        default=None, min_length=1, max_length=200
    )
    emergency_contact_email: str | None = Field(
        default=None, min_length=1, max_length=320
    )
    emergency_contact_phone: str | None = Field(default=None, max_length=50)
    scopes: list[EngagementScopeCreate] | None = None


class KillSwitchRequest(BaseModel):
    """Body for toggling the kill switch on an engagement."""

    model_config = ConfigDict(extra="forbid")

    active: bool
    reason: str = Field(min_length=1, max_length=2000)


class EngagementScopeResponse(BaseModel):
    """Scope as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    authorization_scope_id: UUID | None
    allowed_paths: Any | None = None
    excluded_paths: Any | None = None
    allowed_ports: list[int] | None = None
    rate_limit_per_minute: int | None
    concurrency_limit: int | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class EngagementResponse(BaseModel):
    """Engagement as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    authorization_id: UUID
    name: str
    description: str | None
    status: EngagementStatus
    starts_at: datetime
    ends_at: datetime
    timezone: str
    max_risk_tier: RiskTier
    default_rate_limit_per_minute: int
    default_concurrency_limit: int
    emergency_contact_name: str
    emergency_contact_email: str
    emergency_contact_phone: str | None
    kill_switch_active: bool
    kill_switch_reason: str | None
    activated_at: datetime | None
    paused_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    scopes: list[EngagementScopeResponse]
    created_at: datetime
    updated_at: datetime
