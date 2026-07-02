"""Async database access for the control plane.

Exposes engine and session-factory construction plus an explicit transaction
scope. Transaction boundaries are explicit by design — callers do not rely on
implicit autocommit (see ``.claude/rules/python-style.md``).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import Settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    Alembic autogenerate compares against ``Base.metadata``; domain models must
    import and subclass this so their tables register here.
    """


class TimestampMixin:
    """Server-managed creation and update timestamps.

    Both default to the database clock so the application never invents audit
    times; ``updated_at`` advances on every UPDATE. Timestamps are timezone
    aware to keep cross-region reasoning unambiguous.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine from settings, using the asyncpg driver."""
    dsn = settings.database_dsn.get_secret_value()
    # The DSN is validated in Settings; normalize the bare scheme to asyncpg.
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(dsn, pool_pre_ping=True)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to ``engine``."""
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Run work inside one transaction.

    Commits on clean exit, rolls back on any exception, and always closes the
    session. This is the single, explicit write boundary for the control plane.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
