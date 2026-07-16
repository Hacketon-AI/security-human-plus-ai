"""Alembic environment for SecureScope, async-first.

The database URL is read from application settings at runtime, never from
``alembic.ini``, so credentials are not persisted in a config file. Domain
models are imported below so their tables register on ``Base.metadata`` for
autogenerate; none exist yet.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.modules.asset_verifications import models as asset_verification_models
from app.modules.assets import models as asset_models
from app.modules.auth import models as auth_models
from app.modules.authorizations import models as authorization_models
from app.modules.engagements import models as engagement_models
from app.modules.organizations import models as organization_models
from app.modules.projects import models as project_models
from app.modules.validation_executions import models as validation_execution_models
from app.modules.audit_events import models as audit_event_models
from app.platform.database import Base

# Importing the domain model modules registers their tables on Base.metadata so
# autogenerate can compare against them. The tuple keeps the imports referenced.
_REGISTERED_MODELS = (
    auth_models,
    organization_models,
    project_models,
    asset_models,
    asset_verification_models,
    authorization_models,
    engagement_models,
    validation_execution_models,
    audit_event_models,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    dsn = get_settings().database_dsn.get_secret_value()
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


def run_migrations_offline() -> None:
    """Emit SQL without a live connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live async connection."""
    engine = create_async_engine(_database_url(), pool_pre_ping=True)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
