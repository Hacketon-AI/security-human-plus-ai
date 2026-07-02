"""SQLAlchemy model for organizations."""

import uuid

from sqlalchemy import Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.organizations.enums import OrganizationStatus
from app.platform.database import Base, TimestampMixin


class Organization(TimestampMixin, Base):
    """A tenant root. All projects and assets descend from one organization."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(
            OrganizationStatus,
            name="organization_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=OrganizationStatus.active,
    )
