"""SQLAlchemy models for engagements and engagement scopes."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.authorizations.enums import RiskTier
from app.modules.engagements.enums import EngagementStatus
from app.platform.database import Base, TimestampMixin


class Engagement(TimestampMixin, Base):
    """An operational engagement that gates scanner execution.

    Links to an active authorization and defines the testing window,
    risk tier cap, rate limits, and kill switch state. Execution eligibility
    is determined by status, time window, kill switch, and linked
    authorization validity.
    """

    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("projects.id"), nullable=False, index=True
    )
    authorization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("authorizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[EngagementStatus] = mapped_column(
        Enum(
            EngagementStatus,
            name="engagement_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=EngagementStatus.draft,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    max_risk_tier: Mapped[RiskTier] = mapped_column(
        Enum(
            RiskTier,
            name="risk_tier",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    default_rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    default_concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    emergency_contact_name: Mapped[str] = mapped_column(String(200), nullable=False)
    emergency_contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    kill_switch_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    kill_switch_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    scopes: Mapped[list["EngagementScope"]] = relationship(
        "EngagementScope",
        back_populates="engagement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class EngagementScope(TimestampMixin, Base):
    """A permitted asset target within one engagement.

    Each scope maps one asset to rate limits and path/port boundaries.
    The asset must be verified, belong to the same organization and project,
    and be included in the linked authorization's scope.
    """

    __tablename__ = "engagement_scopes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("engagements.id"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("assets.id"), nullable=False
    )
    authorization_scope_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("authorization_scopes.id"), nullable=True
    )
    allowed_paths: Mapped[object | None] = mapped_column(JSON, nullable=True)
    excluded_paths: Mapped[object | None] = mapped_column(JSON, nullable=True)
    # Structured port allow-list (``list[int]``); same JSON storage as
    # ``AuthorizationScope.allowed_ports``. DB type unchanged — no migration.
    allowed_ports: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    concurrency_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    engagement: Mapped["Engagement"] = relationship(
        "Engagement", back_populates="scopes"
    )
