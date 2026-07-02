"""validation executions and step results

Revision ID: 0005_validation_executions
Revises: 0004_engagements
Create Date: 2026-06-24

Creates the validation_executions table (the controlled execution-request and
validation lifecycle boundary) and validation_step_results. The control plane
records intent and immutable snapshots; scanners run only in isolated workers.
No scanner, payload, or evidence-storage logic is introduced here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_validation_executions"
down_revision: str | None = "0004_engagements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


execution_status = sa.Enum(
    "draft",
    "queued",
    "dispatching",
    "executing",
    "succeeded",
    "failed",
    "cancelled",
    "blocked",
    name="execution_status",
)
execution_outcome = sa.Enum(
    "not_run",
    "validated",
    "not_reproduced",
    "inconclusive",
    "blocked_by_control",
    "failed_safely",
    name="execution_outcome",
)
step_status = sa.Enum(
    "pending",
    "running",
    "passed",
    "failed",
    "skipped",
    "inconclusive",
    name="step_status",
)

# risk_tier already exists (created by 0003_authorizations); reuse it.
risk_tier = sa.Enum(
    "tier_0_passive",
    "tier_1_safe",
    "tier_2_controlled",
    "tier_3_critical",
    name="risk_tier",
)

_ENUMS = (execution_status, execution_outcome, step_status)


def upgrade() -> None:
    op.create_table(
        "validation_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=False),
        sa.Column("authorization_scope_id", sa.Uuid(), nullable=True),
        sa.Column("engagement_id", sa.Uuid(), nullable=False),
        sa.Column("engagement_scope_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            execution_status,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("outcome", execution_outcome, nullable=True),
        sa.Column("requested_by", sa.String(length=200), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("risk_tier", risk_tier, nullable=False),
        sa.Column("execution_specification", sa.JSON(), nullable=False),
        sa.Column("scope_snapshot", sa.JSON(), nullable=False),
        sa.Column("safety_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["authorization_id"], ["authorizations.id"]),
        sa.ForeignKeyConstraint(
            ["authorization_scope_id"], ["authorization_scopes.id"]
        ),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"]),
        sa.ForeignKeyConstraint(["engagement_scope_id"], ["engagement_scopes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_executions_organization_id",
        "validation_executions",
        ["organization_id"],
    )
    op.create_index(
        "ix_validation_executions_project_id",
        "validation_executions",
        ["project_id"],
    )
    op.create_index(
        "ix_validation_executions_asset_id",
        "validation_executions",
        ["asset_id"],
    )
    op.create_index(
        "ix_validation_executions_authorization_id",
        "validation_executions",
        ["authorization_id"],
    )
    op.create_index(
        "ix_validation_executions_engagement_id",
        "validation_executions",
        ["engagement_id"],
    )
    op.create_index(
        "ix_validation_executions_status",
        "validation_executions",
        ["status"],
    )
    op.create_index(
        "ix_validation_executions_created_at",
        "validation_executions",
        ["created_at"],
    )
    # One execution per (organization, idempotency_key) when a key is present.
    op.create_index(
        "uq_validation_execution_idempotency_key",
        "validation_executions",
        ["organization_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "validation_step_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            step_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["execution_id"], ["validation_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_step_results_organization_id",
        "validation_step_results",
        ["organization_id"],
    )
    op.create_index(
        "ix_validation_step_results_execution_id",
        "validation_step_results",
        ["execution_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_validation_step_results_execution_id",
        table_name="validation_step_results",
    )
    op.drop_index(
        "ix_validation_step_results_organization_id",
        table_name="validation_step_results",
    )
    op.drop_table("validation_step_results")
    op.drop_index(
        "uq_validation_execution_idempotency_key",
        table_name="validation_executions",
    )
    op.drop_index(
        "ix_validation_executions_created_at",
        table_name="validation_executions",
    )
    op.drop_index(
        "ix_validation_executions_status",
        table_name="validation_executions",
    )
    op.drop_index(
        "ix_validation_executions_engagement_id",
        table_name="validation_executions",
    )
    op.drop_index(
        "ix_validation_executions_authorization_id",
        table_name="validation_executions",
    )
    op.drop_index(
        "ix_validation_executions_asset_id",
        table_name="validation_executions",
    )
    op.drop_index(
        "ix_validation_executions_project_id",
        table_name="validation_executions",
    )
    op.drop_index(
        "ix_validation_executions_organization_id",
        table_name="validation_executions",
    )
    op.drop_table("validation_executions")
    bind = op.get_bind()
    for enum in reversed(_ENUMS):
        enum.drop(bind, checkfirst=False)
