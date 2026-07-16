"""Shared test fixtures.

Integration and API tests run against a real PostgreSQL instance provided by
Testcontainers so the test database matches production semantics (native enums,
constraints, transactions). There is no SQLite fallback: if Docker or
Testcontainers is unavailable the integration fixtures are reported as skipped
(blocked), never silently substituted.

The schema is created by running the real Alembic migration against the
container, so the migration itself is exercised on every run.
"""

import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    """Start a PostgreSQL container and yield an asyncpg DSN for it.

    Skips (reports blocked) rather than failing when the container cannot be
    started, e.g. Docker is not running.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Testcontainers unavailable (blocked): {exc}")

    try:
        # psycopg is only the readiness driver; the app connects via asyncpg.
        container = PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"PostgreSQL Testcontainer unavailable (blocked): {exc}")

    try:
        dsn = (
            f"postgresql+asyncpg://{container.username}:{container.password}"
            f"@{container.get_container_host_ip()}"
            f":{container.get_exposed_port(5432)}/{container.dbname}"
        )
        yield dsn
    finally:
        container.stop()


@pytest.fixture(scope="session")
def migrated_dsn(postgres_dsn: str) -> str:
    """Apply ``alembic upgrade head`` to the container and return its DSN."""
    os.environ["SECURESCOPE_DATABASE_DSN"] = postgres_dsn
    # The settings cache may have been populated by an earlier import.
    from app.config import get_settings

    get_settings.cache_clear()

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")
    return postgres_dsn


@pytest.fixture
async def engine(migrated_dsn: str) -> AsyncIterator[AsyncEngine]:
    """A per-test engine that starts from a clean schema.

    Truncating before the test yields gives each test an isolated dataset while
    sharing one migrated container for the whole session.
    """
    async_engine = create_async_engine(migrated_dsn)
    async with async_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE asset_verification_challenges, assets, projects, "
                "organizations RESTART IDENTITY CASCADE"
            )
        )
    try:
        yield async_engine
    finally:
        await async_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def client(migrated_dsn: str, engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the app, pointed at the migrated container.

    Depends on ``engine`` so the per-test truncation runs before the app starts.
    """
    from app.config import Environment, Settings
    from app.main import create_app
    from pydantic import SecretStr

    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(migrated_dsn),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_client:
            yield http_client


def tenant_headers(organization_id: str | UUID) -> dict[str, str]:
    """Development tenant header for the given organization."""
    return {"X-Organization-Id": str(organization_id)}


# Worker machine credential used by the test app's worker transition hooks. It
# is an explicit configured test token, never a product default.
WORKER_AUTH_TOKEN = "test-worker-token"


def worker_auth_headers(token: str = WORKER_AUTH_TOKEN) -> dict[str, str]:
    """Machine-auth header for the worker-started/worker-finished hooks."""
    return {"X-Worker-Authorization": token}


@dataclass(frozen=True, slots=True)
class FixedClock:
    """A clock that always returns a fixed instant, for deterministic tests."""

    moment: datetime

    def now(self) -> datetime:
        return self.moment


class FakeDnsResolver:
    """Deterministic DNS TXT resolver for verification tests.

    ``records`` maps an exact record name to the TXT values returned; unknown
    names resolve to no records. Set ``unavailable`` to simulate a transient
    resolver failure (inconclusive outcome).
    """

    def __init__(self) -> None:
        self.records: dict[str, list[str]] = {}
        self.unavailable = False

    async def resolve_txt(self, record_name: str, timeout_seconds: float) -> list[str]:
        if self.unavailable:
            from app.modules.asset_verifications.dns_resolver import (
                DnsResolutionUnavailable,
            )

            raise DnsResolutionUnavailable("test resolver unavailable")
        return list(self.records.get(record_name, []))


@pytest.fixture
async def verification_app(
    migrated_dsn: str, engine: AsyncEngine
) -> AsyncIterator[tuple[AsyncClient, FakeDnsResolver, Any]]:
    """App + client with the DNS resolver overridden by a FakeDnsResolver.

    Yields ``(client, resolver, app)``; tests mutate ``resolver`` and may add
    further dependency overrides (e.g. a fixed clock) on ``app``.
    """
    from app.config import Environment, Settings
    from app.main import create_app
    from app.modules.asset_verifications.dns_resolver import get_dns_txt_resolver
    from pydantic import SecretStr

    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(migrated_dsn),
    )
    app = create_app(settings)
    resolver = FakeDnsResolver()
    app.dependency_overrides[get_dns_txt_resolver] = lambda: resolver
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_client:
            yield http_client, resolver, app


class CapturingValidationDispatcher:
    """Test dispatcher that records the payloads it would dispatch.

    It executes nothing; it only captures the immutable WorkerDispatchPayload so
    tests can assert what the API hands to the worker seam. It also records the
    per-execution credential ``handoff`` it is given (side-channel data) so
    tests can assert the raw token reaches the dispatcher boundary but never
    the broker payload.
    """

    def __init__(self) -> None:
        from app.modules.validation_executions.dispatch_contracts import (
            WorkerDispatchPayload,
        )
        from app.modules.validation_executions.worker_credential_contracts import (
            WorkerCredentialHandoff,
        )

        self.dispatched: list[WorkerDispatchPayload] = []
        self.handoffs: list[WorkerCredentialHandoff | None] = []

    async def dispatch(self, payload: Any, *, handoff: Any = None) -> None:
        self.dispatched.append(payload)
        self.handoffs.append(handoff)


@pytest.fixture
async def validation_app(
    migrated_dsn: str, engine: AsyncEngine
) -> AsyncIterator[tuple[AsyncClient, CapturingValidationDispatcher, Any]]:
    """App + client with the validation dispatcher overridden by a capturing fake.

    Yields ``(client, dispatcher, app)``; tests inspect ``dispatcher.dispatched``
    and may add further dependency overrides (e.g. a fixed clock) on ``app``.
    """
    from app.config import Environment, Settings
    from app.main import create_app
    from app.modules.validation_executions.dispatcher import (
        get_validation_dispatcher,
    )
    from pydantic import SecretStr

    settings = Settings(
        environment=Environment.development,
        database_dsn=SecretStr(migrated_dsn),
        worker_auth_token=SecretStr(WORKER_AUTH_TOKEN),
        # The pre-existing API suite drives worker hooks with the shared
        # ``X-Worker-Authorization`` token. Step 3 makes per-execution
        # credentials the primary auth surface; the shared token now only
        # works behind this explicit transitional flag, so the fixture
        # enables it to keep historical tests covering the un-credential
        # path. Step-3-specific tests assert the default-off behaviour
        # directly via ``app_client``.
        worker_shared_token_fallback_enabled=True,
    )
    app = create_app(settings)
    dispatcher = CapturingValidationDispatcher()
    app.dependency_overrides[get_validation_dispatcher] = lambda: dispatcher
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_client:
            yield http_client, dispatcher, app


@pytest.fixture
def app_client(migrated_dsn: str, engine: AsyncEngine) -> Callable[..., Any]:
    """Return a builder for an HTTP client bound to an app in a given environment.

    Lets tests exercise environment-dependent behaviour (e.g. the development
    adapters being inactive in staging/production). Depends on ``engine`` so the
    per-test truncation runs first.
    """
    from app.config import Environment, Settings
    from app.main import create_app
    from pydantic import SecretStr

    @asynccontextmanager
    async def _build(
        environment: Environment, **overrides: object
    ) -> AsyncIterator[AsyncClient]:
        # Staging/production refuse to start without a worker credential, so a
        # deployed-shaped test app gets the explicit test token unless a test
        # overrides it (e.g. to assert the startup failure directly).
        if environment in (Environment.staging, Environment.production):
            overrides.setdefault("worker_auth_token", SecretStr(WORKER_AUTH_TOKEN))
            overrides.setdefault(
                "jwt_secret", SecretStr("test-only-deployed-jwt-secret")
            )
        settings = Settings(
            environment=environment,
            database_dsn=SecretStr(migrated_dsn),
            **overrides,
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://testserver",
            ) as http_client:
                yield http_client

    return _build


@pytest.fixture
def create_organization(
    client: AsyncClient,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return a helper that creates an organization and returns its payload."""

    async def _create(
        name: str = "Acme Bank", slug: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if slug is not None:
            body["slug"] = slug
        response = await client.post("/api/v1/organizations", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture
def set_organization_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[str, str], Awaitable[None]]:
    """Return a helper that forces an organization's lifecycle status.

    No endpoint sets non-active statuses in this stage, so tests drive the
    lifecycle gates directly against the database.
    """

    async def _set(organization_id: str, status: str) -> None:
        async with session_factory() as session:
            await session.execute(
                text("UPDATE organizations SET status = :status WHERE id = :id"),
                {"status": status, "id": organization_id},
            )
            await session.commit()

    return _set


@pytest.fixture
def set_project_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[str, str], Awaitable[None]]:
    """Return a helper that forces a project's lifecycle status."""

    async def _set(project_id: str, status: str) -> None:
        async with session_factory() as session:
            await session.execute(
                text("UPDATE projects SET status = :status WHERE id = :id"),
                {"status": status, "id": project_id},
            )
            await session.commit()

    return _set


@pytest.fixture
def set_asset_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[str, str], Awaitable[None]]:
    """Return a helper that forces an asset's lifecycle status.

    Suspended/retired/verified states have no endpoint in this stage, so the
    mutation-policy tests drive them directly against the database.
    """

    async def _set(asset_id: str, status: str) -> None:
        async with session_factory() as session:
            await session.execute(
                text("UPDATE assets SET status = :status WHERE id = :id"),
                {"status": status, "id": asset_id},
            )
            await session.commit()

    return _set
