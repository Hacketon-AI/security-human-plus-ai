"""Smoke test for the application factory and liveness probe.

Uses an explicit in-test Settings so it does not depend on the environment.
The dummy DSN is never connected to — the engine connects lazily and the
liveness probe does not touch the database.
"""

from app.config import Environment, Settings
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr


def _test_settings() -> Settings:
    return Settings(
        environment=Environment.development,
        database_dsn=SecretStr(
            "postgresql+asyncpg://securescope:secret@localhost:5432/securescope"
        ),
    )


async def test_healthz_reports_ok() -> None:
    app = create_app(_test_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
