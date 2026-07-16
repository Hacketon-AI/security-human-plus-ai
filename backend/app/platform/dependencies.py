"""FastAPI dependencies for the platform layer.

Provides the single transactional database session used by request handlers.
The transaction boundary is explicit (see ``app.platform.database.transaction``):
the session commits when the handler returns cleanly and rolls back if it
raises, so use cases never rely on implicit autocommit.
"""

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.platform.database import transaction


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session inside one transaction.

    The session factory is owned by the application lifespan and stored on
    ``app.state``; see ``app.main.create_app``.
    """
    async with transaction(request.app.state.session_factory) as session:
        yield session


# Alias for the auth module — same implementation, clearer name.
async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session (alias used by auth module)."""
    async with transaction(request.app.state.session_factory) as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    """Return the immutable settings bound to the running application.

    Adapters use this to make environment-dependent decisions (e.g. whether the
    development tenant/provisioning adapters are in effect). ``app.state`` is
    untyped, so the value is cast back to the known ``Settings`` type.
    """
    return cast(Settings, request.app.state.settings)


def get_jwt_secret(request: Request) -> str:
    """Return the JWT signing secret from application settings."""
    settings = cast(Settings, request.app.state.settings)
    return settings.jwt_secret.get_secret_value()
