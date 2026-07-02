"""authorization_scopes.allowed_ports to structured JSON list[int]

Revision ID: 0006_auth_scope_ports_json
Revises: 0005_validation_executions
Create Date: 2026-06-25

The original ``allowed_ports`` column was free-text ``String(500)``. The worker
execution snapshot requires a structured ``list[int]`` port allow-list (matching
``engagement_scopes.allowed_ports``), so a stray string can never reach an
isolated worker. This recreates the column as JSON.

Legacy free-text values are intentionally not machine-converted: parsing
arbitrary comma-separated text into ports is explicitly out of scope (see
``.claude/rules/scan-authorization.md`` — never weaken the scope contract), and
no structured representation exists to preserve. On the current development
schema the column carries no production data, so the column is dropped and
re-added as nullable JSON; any pre-existing free-text value is discarded rather
than silently reinterpreted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_auth_scope_ports_json"
down_revision: str | None = "0005_validation_executions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("authorization_scopes", "allowed_ports")
    op.add_column(
        "authorization_scopes",
        sa.Column("allowed_ports", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("authorization_scopes", "allowed_ports")
    op.add_column(
        "authorization_scopes",
        sa.Column("allowed_ports", sa.String(length=500), nullable=True),
    )
