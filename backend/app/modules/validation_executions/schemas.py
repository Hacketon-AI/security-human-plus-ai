"""Pydantic request/response models for the validation-executions API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.authorizations.enums import RiskTier
from app.modules.validation_executions.enums import (
    ExecutionOutcome,
    ExecutionStatus,
    StepStatus,
)


class ValidationExecutionCreate(BaseModel):
    """Body for creating and queueing a validation execution.

    ``organization_id`` is never accepted — ownership comes from the tenant
    context. ``status``/snapshots are server-derived and never client-supplied.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    asset_id: UUID
    authorization_id: UUID
    engagement_id: UUID
    engagement_scope_id: UUID
    template_id: str = Field(min_length=1, max_length=100)
    requested_by: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class WorkerStepResult(BaseModel):
    """A single sanitized step result reported by the worker."""

    model_config = ConfigDict(extra="forbid")

    step_name: str = Field(min_length=1, max_length=200)
    status: StepStatus
    evidence: dict[str, Any] | None = None


class WorkerFinishedRequest(BaseModel):
    """Result body reported by the worker on completion.

    Only sanitized fields are accepted; the service sanitizes again at the
    boundary before persisting. ``outcome`` records the validation verdict;
    ``status`` is constrained to terminal run states by the service.
    """

    model_config = ConfigDict(extra="forbid")

    succeeded: bool
    outcome: ExecutionOutcome
    result_summary: str | None = Field(default=None, max_length=4000)
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, max_length=2000)
    steps: list[WorkerStepResult] = Field(default_factory=list)


class WorkerExecutionStateResponse(BaseModel):
    """Minimal execution state returned to a worker after a transition hook.

    Worker hooks are machine endpoints. Their response must not echo the
    immutable specification, scope/safety snapshots, kill-switch token, step
    evidence, or any worker credential back over the wire — the worker already
    holds what it needs and nothing sensitive should be reflected. Only the
    lifecycle state needed to confirm the transition is returned. ``id`` is the
    execution id, matching the identifier field used across the API.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ExecutionStatus
    outcome: ExecutionOutcome | None
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class ValidationStepResultResponse(BaseModel):
    """Step result as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step_name: str
    status: StepStatus
    evidence: Any | None = None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ValidationExecutionResponse(BaseModel):
    """Validation execution as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    asset_id: UUID
    authorization_id: UUID
    authorization_scope_id: UUID | None
    engagement_id: UUID
    engagement_scope_id: UUID
    template_id: str
    status: ExecutionStatus
    outcome: ExecutionOutcome | None
    requested_by: str | None
    idempotency_key: str | None
    risk_tier: RiskTier
    execution_specification: Any
    scope_snapshot: Any
    safety_snapshot: Any
    result_summary: str | None
    error_code: str | None
    error_message: str | None
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    step_results: list[ValidationStepResultResponse]
    created_at: datetime
    updated_at: datetime
