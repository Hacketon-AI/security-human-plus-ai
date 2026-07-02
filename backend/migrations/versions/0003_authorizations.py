"""authorizations and authorization scopes

Revision ID: 0003_authorizations
Revises: 0002_asset_verifications
Create Date: 2026-06-23

Creates the authorizations table for recorded written security-testing
authorizations and authorization_scopes for per-asset rate limits and
scope boundaries. Document storage (S3) is deferred; only the SHA-256
digest and document name are persisted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_authorizations"
down_revision: str | None = "0002_asset_verifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


authorization_status = sa.Enum(
    "draft",
    "submitted",
    "active",
    "expired",
    "revoked",
    "rejected",
    name="authorization_status",
)

risk_tier = sa.Enum(
    "tier_0_passive",
    "tier_1_safe",
    "tier_2_controlled",
    "tier_3_critical",
    name="risk_tier",
)

_ENUMS = (authorization_status, risk_tier)


def upgrade() -> None:
    op.create_table(
        "authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("reference_number", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            authorization_status,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("maximum_risk_tier", risk_tier, nullable=False),
        sa.Column(
            "production_testing_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "core_banking_testing_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("emergency_contact_name", sa.String(length=200), nullable=False),
        sa.Column("emergency_contact_phone", sa.String(length=50), nullable=False),
        sa.Column(
            "authorization_document_name",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "authorization_document_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "authorization_document_reference",
            sa.String(length=2000),
            nullable=True,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=2000), nullable=True),
        sa.Column("revocation_reason", sa.String(length=2000), nullable=True),
        sa.Column("activated_by_reference", sa.String(length=500), nullable=True),
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
    op.create_index(
        "ix_authorizations_organization_id",
        "authorizations",
        ["organization_id"],
    )
    op.create_index(
        "ix_authorizations_project_id",
        "authorizations",
        ["project_id"],
    )

    op.create_table(
        "authorization_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("allowed_ports", sa.String(length=500), nullable=True),
        sa.Column("allowed_paths", sa.String(length=2000), nullable=True),
        sa.Column("excluded_paths", sa.String(length=2000), nullable=True),
        sa.Column("maximum_requests_per_minute", sa.Integer(), nullable=False),
        sa.Column("maximum_concurrency", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["authorization_id"], ["authorizations.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "authorization_id",
            "asset_id",
            name="uq_authorization_scope_asset",
        ),
    )
    op.create_index(
        "ix_authorization_scopes_organization_id",
        "authorization_scopes",
        ["organization_id"],
    )
    op.create_index(
        "ix_authorization_scopes_authorization_id",
        "authorization_scopes",
        ["authorization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_authorization_scopes_authorization_id",
        table_name="authorization_scopes",
    )
    op.drop_index(
        "ix_authorization_scopes_organization_id",
        table_name="authorization_scopes",
    )
    op.drop_table("authorization_scopes")
    op.drop_index(
        "ix_authorizations_project_id",
        table_name="authorizations",
    )
    op.drop_index(
        "ix_authorizations_organization_id",
        table_name="authorizations",
    )
    op.drop_table("authorizations")
    bind = op.get_bind()
    for enum in reversed(_ENUMS):
        enum.drop(bind, checkfirst=False)
