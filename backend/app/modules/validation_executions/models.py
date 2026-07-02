"""SQLAlchemy models for validation executions and step results."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.authorizations.enums import RiskTier
from app.modules.validation_executions.enums import (
    ExecutionOutcome,
    ExecutionStatus,
    StepStatus,
)
from app.platform.database import Base, TimestampMixin


class ValidationExecution(TimestampMixin, Base):
    """A recorded request to run one safe validation against one asset.

    The control plane owns this lifecycle; the actual check runs in an isolated
    worker. The execution carries immutable snapshots (specification, scope,
    safety) frozen at queue time so later edits to the source rows never change
    what was authorized.
    """

    __tablename__ = "validation_executions"
    __table_args__ = (
        # At most one execution per (organization, idempotency_key) when a key
        # is supplied; NULL keys are unconstrained.
        Index(
            "uq_validation_execution_idempotency_key",
            "organization_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_validation_executions_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("projects.id"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("assets.id"), nullable=False, index=True
    )
    authorization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("authorizations.id"), nullable=False, index=True
    )
    authorization_scope_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("authorization_scopes.id"), nullable=True
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("engagements.id"), nullable=False, index=True
    )
    engagement_scope_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("engagement_scopes.id"), nullable=False
    )
    template_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(
            ExecutionStatus,
            name="execution_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=ExecutionStatus.draft,
        index=True,
    )
    outcome: Mapped[ExecutionOutcome | None] = mapped_column(
        Enum(
            ExecutionOutcome,
            name="execution_outcome",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=True,
    )
    requested_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    risk_tier: Mapped[RiskTier] = mapped_column(
        Enum(
            RiskTier,
            name="risk_tier",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    execution_specification: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    scope_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    safety_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    step_results: Mapped[list["ValidationStepResult"]] = relationship(
        "ValidationStepResult",
        back_populates="execution",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ValidationStepResult(TimestampMixin, Base):
    """One step within a validation execution, with sanitized evidence."""

    __tablename__ = "validation_step_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("validation_executions.id"), nullable=False, index=True
    )
    step_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(
            StepStatus,
            name="step_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=StepStatus.pending,
    )
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    execution: Mapped["ValidationExecution"] = relationship(
        "ValidationExecution", back_populates="step_results"
    )


class ValidationWorkerCredential(TimestampMixin, Base):
    """Server-side row for one per-execution worker credential.

    The credential authorizes an isolated worker against the
    ``worker-started`` / ``worker-finished`` hooks for a single execution.
    The control plane stores only the SHA-256 ``token_digest``; the raw
    token is returned exactly once by the issuer and reaches the worker via
    a side-channel — never via the broker envelope, the dispatch payload,
    or any persisted column (see
    ``docs/validation-worker-credentials-design.md``).

    ``allowed_actions`` is a JSON list of :class:`WorkerHookAction` values
    so a credential can be issued for just one hook if needed (defensive
    least-privilege). The unique index on ``token_digest`` makes the
    digest-keyed verifier lookup unambiguous and rejects accidental
    collisions at the DB level.
    """

    __tablename__ = "validation_worker_credentials"
    __table_args__ = (
        Index(
            "uq_validation_worker_credential_token_digest",
            "token_digest",
            unique=True,
        ),
        Index(
            "ix_validation_worker_credentials_organization_id",
            "organization_id",
        ),
        Index(
            "ix_validation_worker_credentials_execution_id",
            "execution_id",
        ),
        Index(
            "ix_validation_worker_credentials_expires_at",
            "expires_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("validation_executions.id"), nullable=False
    )
    # SHA-256 hex digest: always 64 chars over [0-9a-f]. The raw token is
    # NEVER stored. The unique index above prevents accidental reuse and
    # makes the verifier's digest lookup deterministic.
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
