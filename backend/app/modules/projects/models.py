"""SQLAlchemy model for projects."""

import uuid

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.projects.enums import ProjectStatus
from app.platform.database import Base, TimestampMixin


class Project(TimestampMixin, Base):
    """A project owned by one organization; assets live under projects."""

    __tablename__ = "projects"
    __table_args__ = (
        # Slugs are unique per tenant, not globally.
        UniqueConstraint("organization_id", "slug", name="uq_project_org_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(
            ProjectStatus,
            name="project_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=ProjectStatus.active,
    )
