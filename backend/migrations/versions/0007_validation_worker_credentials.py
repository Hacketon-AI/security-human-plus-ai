"""Validation worker credentials.

Persists the server-side row for one per-execution worker credential. The
control plane stores only the SHA-256 ``token_digest``; the raw token is
returned exactly once by the issuer and reaches the worker via a side-channel.
The unique index on ``token_digest`` makes the verifier's lookup
deterministic and prevents accidental reuse at the DB level.

See ``docs/validation-worker-credentials-design.md`` → rollout Step 2.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_worker_credentials"
down_revision: str | None = "0006_auth_scope_ports_json"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validation_worker_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        # SHA-256 hex digest: always 64 chars. NEVER the raw token.
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        # JSON list of WorkerHookAction values (``worker_started`` /
        # ``worker_finished``). A credential may grant one or both.
        sa.Column("allowed_actions", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        "uq_validation_worker_credential_token_digest",
        "validation_worker_credentials",
        ["token_digest"],
        unique=True,
    )
    op.create_index(
        "ix_validation_worker_credentials_organization_id",
        "validation_worker_credentials",
        ["organization_id"],
    )
    op.create_index(
        "ix_validation_worker_credentials_execution_id",
        "validation_worker_credentials",
        ["execution_id"],
    )
    op.create_index(
        "ix_validation_worker_credentials_expires_at",
        "validation_worker_credentials",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_validation_worker_credentials_expires_at",
        table_name="validation_worker_credentials",
    )
    op.drop_index(
        "ix_validation_worker_credentials_execution_id",
        table_name="validation_worker_credentials",
    )
    op.drop_index(
        "ix_validation_worker_credentials_organization_id",
        table_name="validation_worker_credentials",
    )
    op.drop_index(
        "uq_validation_worker_credential_token_digest",
        table_name="validation_worker_credentials",
    )
    op.drop_table("validation_worker_credentials")
