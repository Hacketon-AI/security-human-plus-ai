"""asset verification challenges (DNS TXT)

Revision ID: 0002_asset_verifications
Revises: 0001_foundation
Create Date: 2026-06-23

Adds DNS TXT ownership-verification challenges. A partial unique index enforces
at most one pending challenge per asset. Only digests of the expected TXT value
are stored; the raw token is never persisted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_asset_verifications"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


challenge_method = sa.Enum("dns_txt", name="challenge_method")
challenge_status = sa.Enum(
    "pending", "verified", "expired", "failed", "cancelled", name="challenge_status"
)

_ENUMS = (challenge_method, challenge_status)


def upgrade() -> None:
    op.create_table(
        "asset_verification_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("method", challenge_method, nullable=False, server_default="dns_txt"),
        sa.Column("status", challenge_status, nullable=False, server_default="pending"),
        sa.Column("record_name", sa.String(length=255), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("token_last_four", sa.String(length=4), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maximum_attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_asset_verification_challenges_organization_id",
        "asset_verification_challenges",
        ["organization_id"],
    )
    op.create_index(
        "ix_asset_verification_challenges_project_id",
        "asset_verification_challenges",
        ["project_id"],
    )
    op.create_index(
        "ix_asset_verification_challenges_asset_id",
        "asset_verification_challenges",
        ["asset_id"],
    )
    # At most one pending challenge per asset; the database is the source of
    # truth for this invariant under concurrent creates.
    op.create_index(
        "uq_one_pending_challenge_per_asset",
        "asset_verification_challenges",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_one_pending_challenge_per_asset",
        table_name="asset_verification_challenges",
    )
    op.drop_index(
        "ix_asset_verification_challenges_asset_id",
        table_name="asset_verification_challenges",
    )
    op.drop_index(
        "ix_asset_verification_challenges_project_id",
        table_name="asset_verification_challenges",
    )
    op.drop_index(
        "ix_asset_verification_challenges_organization_id",
        table_name="asset_verification_challenges",
    )
    op.drop_table("asset_verification_challenges")
    bind = op.get_bind()
    for enum in reversed(_ENUMS):
        enum.drop(bind, checkfirst=False)
