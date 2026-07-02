"""Pydantic request/response models for the authorizations API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.authorizations.enums import AuthorizationStatus, RiskTier
from app.modules.shared.network_ports import AllowedPortList


class AuthorizationScopeCreate(BaseModel):
    """Scope definition for one asset within an authorization."""

    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    allowed_ports: AllowedPortList = None
    allowed_paths: str | None = Field(default=None, max_length=2000)
    excluded_paths: str | None = Field(default=None, max_length=2000)
    maximum_requests_per_minute: int = Field(ge=1)
    maximum_concurrency: int = Field(ge=1)
    notes: str | None = Field(default=None, max_length=2000)


class AuthorizationCreate(BaseModel):
    """Body for creating an authorization (always starts as draft).

    ``organization_id`` is never accepted — ownership comes from the tenant
    context. ``status`` is never accepted — it always starts as ``draft``.
    """

    model_config = ConfigDict(extra="forbid")

    reference_number: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    valid_from: datetime
    valid_until: datetime
    timezone: str = Field(min_length=1, max_length=50)
    maximum_risk_tier: RiskTier
    production_testing_allowed: bool = False
    core_banking_testing_allowed: bool = False
    emergency_contact_name: str = Field(min_length=1, max_length=200)
    emergency_contact_phone: str = Field(min_length=1, max_length=50)
    authorization_document_name: str = Field(min_length=1, max_length=500)
    authorization_document_sha256: str = Field(
        min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$"
    )
    authorization_document_reference: str | None = Field(default=None, max_length=2000)
    scopes: list[AuthorizationScopeCreate] = Field(min_length=1)


class AuthorizationUpdate(BaseModel):
    """Body for updating a draft authorization. All fields are optional;
    only the supplied fields are changed.

    Scopes, when supplied, replace all existing scopes.
    """

    model_config = ConfigDict(extra="forbid")

    reference_number: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=50)
    maximum_risk_tier: RiskTier | None = None
    production_testing_allowed: bool | None = None
    core_banking_testing_allowed: bool | None = None
    emergency_contact_name: str | None = Field(
        default=None, min_length=1, max_length=200
    )
    emergency_contact_phone: str | None = Field(
        default=None, min_length=1, max_length=50
    )
    authorization_document_name: str | None = Field(
        default=None, min_length=1, max_length=500
    )
    authorization_document_sha256: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$"
    )
    authorization_document_reference: str | None = Field(default=None, max_length=2000)
    scopes: list[AuthorizationScopeCreate] | None = None


class AuthorizationReject(BaseModel):
    """Body for rejecting a submitted authorization."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class AuthorizationRevoke(BaseModel):
    """Body for revoking an active authorization."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class AuthorizationScopeResponse(BaseModel):
    """Scope as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    allowed_ports: list[int] | None
    allowed_paths: str | None
    excluded_paths: str | None
    maximum_requests_per_minute: int
    maximum_concurrency: int
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AuthorizationResponse(BaseModel):
    """Authorization as returned by the API.

    Document SHA-256 is included — it is not a secret. The raw document
    is never returned.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    reference_number: str
    title: str
    description: str | None
    status: AuthorizationStatus
    valid_from: datetime
    valid_until: datetime
    timezone: str
    maximum_risk_tier: RiskTier
    production_testing_allowed: bool
    core_banking_testing_allowed: bool
    emergency_contact_name: str
    emergency_contact_phone: str
    authorization_document_name: str
    authorization_document_sha256: str
    authorization_document_reference: str | None
    submitted_at: datetime | None
    activated_at: datetime | None
    revoked_at: datetime | None
    rejection_reason: str | None
    revocation_reason: str | None
    scopes: list[AuthorizationScopeResponse]
    created_at: datetime
    updated_at: datetime
