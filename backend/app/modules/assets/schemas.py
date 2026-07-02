"""Pydantic request/response models for the assets API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.assets.enums import (
    AssetCriticality,
    AssetEnvironment,
    AssetStatus,
    AssetType,
    VerificationMethod,
)


class AssetCreate(BaseModel):
    """Body for registering an asset under a project.

    ``project_id`` selects the owning project; the organization is taken from
    the tenant context. ``status`` is not accepted — assets always start as
    ``draft``. ``extra="forbid"`` rejects unexpected fields, including any
    attempt to set ``organization_id`` or ``status`` directly.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    name: str = Field(min_length=1, max_length=200)
    asset_type: AssetType
    environment: AssetEnvironment
    target: str = Field(min_length=1, max_length=500)
    criticality: AssetCriticality


class AssetUpdate(BaseModel):
    """Body for editing mutable asset metadata.

    Only display name and criticality are editable here. Status changes go
    through explicit lifecycle use cases, not this endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    criticality: AssetCriticality | None = None


class AssetVerificationRequest(BaseModel):
    """Body for requesting ownership verification of a draft asset."""

    model_config = ConfigDict(extra="forbid")

    method: VerificationMethod


class AssetResponse(BaseModel):
    """Asset as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    asset_type: AssetType
    environment: AssetEnvironment
    target: str
    criticality: AssetCriticality
    status: AssetStatus
    ownership_verified_at: datetime | None
    verification_method: VerificationMethod | None
    verification_requested_at: datetime | None
    created_at: datetime
    updated_at: datetime
