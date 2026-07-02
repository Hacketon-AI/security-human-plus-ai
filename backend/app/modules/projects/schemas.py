"""Pydantic request/response models for the projects API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.projects.enums import ProjectStatus


class ProjectCreate(BaseModel):
    """Body for creating a project.

    There is no ``organization_id`` field: ownership comes from the tenant
    context, and ``extra="forbid"`` rejects any client attempt to supply one.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class ProjectResponse(BaseModel):
    """Project as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    slug: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
