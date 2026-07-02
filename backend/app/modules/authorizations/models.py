"""SQLAlchemy models for authorizations and authorization scopes."""

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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.authorizations.enums import AuthorizationStatus, RiskTier
from app.platform.database import Base, TimestampMixin


class Authorization(TimestampMixin, Base):
    """A written, recorded authorization to perform security testing.

    Owned by a project within an organization. Status transitions are
    enforced by the service layer, not the database.
    """

    __tablename__ = "authorizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("projects.id"), nullable=False, index=True
    )
    reference_number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[AuthorizationStatus] = mapped_column(
        Enum(
            AuthorizationStatus,
            name="authorization_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=AuthorizationStatus.draft,
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    maximum_risk_tier: Mapped[RiskTier] = mapped_column(
        Enum(
            RiskTier,
            name="risk_tier",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    production_testing_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    core_banking_testing_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    emergency_contact_name: Mapped[str] = mapped_column(String(200), nullable=False)
    emergency_contact_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    authorization_document_name: Mapped[str] = mapped_column(
        String(500), nullable=False
    )
    authorization_document_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    authorization_document_reference: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    activated_by_reference: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    scopes: Mapped[list["AuthorizationScope"]] = relationship(
        "AuthorizationScope",
        back_populates="authorization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AuthorizationScope(TimestampMixin, Base):
    """A permitted asset target within one authorization.

    Maps one asset to rate limits and scope boundaries. Each scope must
    reference a verified, non-suspended, non-retired asset owned by the
    same organization and project as the authorization.
    """

    __tablename__ = "authorization_scopes"
    __table_args__ = (
        UniqueConstraint(
            "authorization_id",
            "asset_id",
            name="uq_authorization_scope_asset",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    authorization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("authorizations.id"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("assets.id"), nullable=False
    )
    # Structured port allow-list (``list[int]``), matching ``EngagementScope``.
    # Stored as JSON so the worker snapshot carries integers, never free text.
    allowed_ports: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    allowed_paths: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    excluded_paths: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    maximum_requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_concurrency: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    authorization: Mapped["Authorization"] = relationship(
        "Authorization", back_populates="scopes"
    )
