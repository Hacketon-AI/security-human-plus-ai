"""Pydantic request/response models for the organizations API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.organizations.enums import OrganizationStatus


class OrganizationCreate(BaseModel):
    """Body for creating an organization (tenant bootstrap).

    ``extra="forbid"`` rejects unexpected fields at the edge. ``slug`` is
    optional; when omitted it is derived from ``name`` by the service.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100)


class OrganizationResponse(BaseModel):
    """Organization as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime
