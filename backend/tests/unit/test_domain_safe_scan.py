from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from app.config import Environment, Settings, ValidationDispatcherBackend
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

_TEST_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(
        environment=Environment.test,
        database_dsn=SecretStr(
            "postgresql+asyncpg://test:test@localhost:5432/securescope_test"
        ),
        bootstrap_admin_email=None,
        bootstrap_admin_username=None,
        bootstrap_admin_password=None,
        bootstrap_admin_organization_id=None,
        bootstrap_admin_full_name=None,
        validation_dispatcher_backend=ValidationDispatcherBackend.unconfigured,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Organization-Id": str(_TEST_ORGANIZATION_ID)},
        ) as http_client:
            yield http_client


async def test_domain_safe_scan_unauthorized(client: AsyncClient) -> None:
    response = await client.post(
        "/domain-safe-scan/analyze",
        json={"domain": "example.com", "scheme": "https", "confirm_authorized": False},
    )
    assert response.status_code == 400
    assert "Scan not authorized" in response.json()["detail"]


async def test_domain_safe_scan_localhost(client: AsyncClient) -> None:
    response = await client.post(
        "/domain-safe-scan/analyze",
        json={"domain": "localhost", "scheme": "http", "confirm_authorized": True},
    )
    assert response.status_code == 400
    assert "Local or internal domains" in response.json()["detail"]


async def test_domain_safe_scan_private_ip(client: AsyncClient) -> None:
    response = await client.post(
        "/domain-safe-scan/analyze",
        json={"domain": "127.0.0.1", "scheme": "http", "confirm_authorized": True},
    )
    assert response.status_code == 400
    assert (
        "private" in response.json()["detail"]
        or "loopback" in response.json()["detail"]
    )
