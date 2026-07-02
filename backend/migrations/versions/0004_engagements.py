"""engagements and engagement scopes

Revision ID: 0004_engagements
Revises: 0003_authorizations
Create Date: 2026-06-23

Creates the engagements table for operational engagement tracking and
engagement_scopes for per-asset scope boundaries within an engagement.
Engagements gate scanner execution — the engagement must be active with
a valid kill-switch state before any scan may be dispatched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_engagements"
down_revision: str | None = "0003_authorizations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


engagement_status = sa.Enum(
    "draft",
    "scheduled",
    "active",
    "paused",
    "completed",
    "cancelled",
    name="engagement_status",
)

# risk_tier is already created by 0003_authorizations; reuse the existing type.
risk_tier = sa.Enum(
    "tier_0_passive",
    "tier_1_safe",
    "tier_2_controlled",
    "tier_3_critical",
    name="risk_tier",
)

_ENUMS = (engagement_status,)


def upgrade() -> None:
    op.create_table(
        "engagements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            engagement_status,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("max_risk_tier", risk_tier, nullable=False),
        sa.Column("default_rate_limit_per_minute", sa.Integer(), nullable=False),
        sa.Column("default_concurrency_limit", sa.Integer(), nullable=False),
        sa.Column("emergency_contact_name", sa.String(length=200), nullable=False),
        sa.Column("emergency_contact_email", sa.String(length=320), nullable=False),
        sa.Column("emergency_contact_phone", sa.String(length=50), nullable=True),
        sa.Column(
            "kill_switch_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("kill_switch_reason", sa.String(length=2000), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["authorization_id"], ["authorizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_engagements_organization_id",
        "engagements",
        ["organization_id"],
    )
    op.create_index(
        "ix_engagements_project_id",
        "engagements",
        ["project_id"],
    )
    op.create_index(
        "ix_engagements_authorization_id",
        "engagements",
        ["authorization_id"],
    )
    op.create_index(
        "ix_engagements_status",
        "engagements",
        ["status"],
    )

    op.create_table(
        "engagement_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("engagement_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_scope_id", sa.Uuid(), nullable=True),
        sa.Column("allowed_paths", sa.JSON(), nullable=True),
        sa.Column("excluded_paths", sa.JSON(), nullable=True),
        sa.Column("allowed_ports", sa.JSON(), nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("concurrency_limit", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
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
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(
            ["authorization_scope_id"], ["authorization_scopes.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_engagement_scopes_organization_id",
        "engagement_scopes",
        ["organization_id"],
    )
    op.create_index(
        "ix_engagement_scopes_engagement_id",
        "engagement_scopes",
        ["engagement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_engagement_scopes_engagement_id",
        table_name="engagement_scopes",
    )
    op.drop_index(
        "ix_engagement_scopes_organization_id",
        table_name="engagement_scopes",
    )
    op.drop_table("engagement_scopes")
    op.drop_index("ix_engagements_status", table_name="engagements")
    op.drop_index("ix_engagements_authorization_id", table_name="engagements")
    op.drop_index("ix_engagements_project_id", table_name="engagements")
    op.drop_index("ix_engagements_organization_id", table_name="engagements")
    op.drop_table("engagements")
    bind = op.get_bind()
    for enum in reversed(_ENUMS):
        enum.drop(bind, checkfirst=False)
