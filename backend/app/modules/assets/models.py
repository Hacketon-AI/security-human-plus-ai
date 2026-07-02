"""SQLAlchemy model for assets."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.assets.enums import (
    AssetCriticality,
    AssetEnvironment,
    AssetStatus,
    AssetType,
    VerificationMethod,
)
from app.platform.database import Base, TimestampMixin


class Asset(TimestampMixin, Base):
    """A registered target. In this stage it is metadata only: an asset is
    registered and may request verification, but is never scanned or executed.
    """

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(
            AssetType,
            name="asset_type",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    environment: Mapped[AssetEnvironment] = mapped_column(
        Enum(
            AssetEnvironment,
            name="asset_environment",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    criticality: Mapped[AssetCriticality] = mapped_column(
        Enum(
            AssetCriticality,
            name="asset_criticality",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    status: Mapped[AssetStatus] = mapped_column(
        Enum(
            AssetStatus,
            name="asset_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=AssetStatus.draft,
    )
    # Set only by the (future) verification use case; never by a client.
    ownership_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The method requested when verification was asked for, recorded for the
    # later challenge/proof flow.
    verification_method: Mapped[VerificationMethod | None] = mapped_column(
        Enum(
            VerificationMethod,
            name="verification_method",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=True,
    )
    verification_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
