"""Pydantic request/response models for the audit-events API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditEventCreate(BaseModel):
    """Body for recording an audit event. organization_id comes from tenant context."""

    model_config = ConfigDict(extra="forbid")

    actor: str = Field(max_length=200)
    actor_type: str = Field(max_length=50)
    action: str = Field(max_length=200)
    entity_type: str = Field(max_length=100)
    entity_id: str = Field(max_length=200)
    execution_id: str | None = Field(default=None, max_length=200)
    safe_metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEventResponse(BaseModel):
    """Audit event as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    at: datetime
    actor: str
    actor_type: str
    action: str
    entity_type: str
    entity_id: str
    execution_id: str | None
    safe_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
