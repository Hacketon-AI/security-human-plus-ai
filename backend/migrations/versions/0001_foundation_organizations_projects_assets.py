"""organizations, projects, assets foundation

Revision ID: 0001_foundation
Revises:
Create Date: 2026-06-23

Creates the tenant hierarchy (organization -> project -> asset) with native
PostgreSQL enum types. Assets are metadata only at this stage; no scan or
execution structures are introduced.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


organization_status = sa.Enum(
    "active", "suspended", "archived", name="organization_status"
)
project_status = sa.Enum("active", "suspended", "archived", name="project_status")
asset_type = sa.Enum(
    "web_application",
    "api",
    "mobile_application",
    "ip_address",
    "cidr_range",
    "repository",
    "service",
    name="asset_type",
)
asset_environment = sa.Enum(
    "development", "staging", "preproduction", "production", name="asset_environment"
)
asset_criticality = sa.Enum(
    "low", "medium", "high", "critical", name="asset_criticality"
)
asset_status = sa.Enum(
    "draft",
    "pending_verification",
    "verified",
    "suspended",
    "retired",
    name="asset_status",
)
verification_method = sa.Enum(
    "dns_txt_record", "http_file", "manual_attestation", name="verification_method"
)

_ENUMS = (
    organization_status,
    project_status,
    asset_type,
    asset_environment,
    asset_criticality,
    asset_status,
    verification_method,
)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column(
            "status", organization_status, nullable=False, server_default="active"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_organization_slug"),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", project_status, nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_project_org_slug"),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])

    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("asset_type", asset_type, nullable=False),
        sa.Column("environment", asset_environment, nullable=False),
        sa.Column("target", sa.String(length=500), nullable=False),
        sa.Column("criticality", asset_criticality, nullable=False),
        sa.Column("status", asset_status, nullable=False, server_default="draft"),
        sa.Column("ownership_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_method", verification_method, nullable=True),
        sa.Column(
            "verification_requested_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_organization_id", "assets", ["organization_id"])
    op.create_index("ix_assets_project_id", "assets", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_assets_project_id", table_name="assets")
    op.drop_index("ix_assets_organization_id", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_table("projects")
    op.drop_table("organizations")
    bind = op.get_bind()
    for enum in reversed(_ENUMS):
        enum.drop(bind, checkfirst=False)
