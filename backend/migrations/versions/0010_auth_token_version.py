"""Add token version to users.

Revision ID: 0010_auth_token_version
Revises: 0009_users_auth
Create Date: 2026-07-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_auth_token_version"
down_revision = "0009_users_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
