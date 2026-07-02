"""SQLAlchemy model for asset verification challenges."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.asset_verifications.enums import ChallengeMethod, ChallengeStatus
from app.platform.database import Base, TimestampMixin


class AssetVerificationChallenge(TimestampMixin, Base):
    """A DNS TXT ownership-proof challenge for one asset.

    Stores only the digest of the expected TXT value and the token's last four
    characters; the raw token is never persisted. A partial unique index keeps
    at most one ``pending`` challenge per asset (the database is the source of
    truth for that invariant).
    """

    __tablename__ = "asset_verification_challenges"
    __table_args__ = (
        Index(
            "uq_one_pending_challenge_per_asset",
            "asset_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
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
    method: Mapped[ChallengeMethod] = mapped_column(
        Enum(
            ChallengeMethod,
            name="challenge_method",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=ChallengeMethod.dns_txt,
    )
    status: Mapped[ChallengeStatus] = mapped_column(
        Enum(
            ChallengeStatus,
            name="challenge_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=ChallengeStatus.pending,
    )
    record_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 hex digest of the expected TXT value; never the raw token.
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    token_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maximum_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
