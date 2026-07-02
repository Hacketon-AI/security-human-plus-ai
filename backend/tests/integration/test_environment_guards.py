"""Environment guards for the development tenant and provisioning adapters."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from app.config import Environment, Settings
from pydantic import SecretStr, ValidationError
from tests.conftest import tenant_headers

_DSN = "postgresql+asyncpg://securescope:secret@localhost:5432/securescope"


def _settings(environment: Environment, **overrides: object) -> Settings:
    return Settings(environment=environment, database_dsn=SecretStr(_DSN), **overrides)


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_enabling_dev_auth_outside_dev_fails_startup(environment: Environment) -> None:
    with pytest.raises(ValidationError):
        _settings(environment, development_auth_enabled=True)


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_enabling_dev_provisioning_outside_dev_fails_startup(
    environment: Environment,
) -> None:
    with pytest.raises(ValidationError):
        _settings(environment, development_provisioning_enabled=True)


@pytest.mark.parametrize("environment", [Environment.development, Environment.test])
def test_dev_adapters_active_by_default_in_dev_and_test(
    environment: Environment,
) -> None:
    settings = _settings(environment)
    assert settings.development_auth_active is True
    assert settings.development_provisioning_active is True


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_dev_adapters_inactive_by_default_outside_dev(
    environment: Environment,
) -> None:
    # Deployed environments require a worker token to start; supply one so this
    # test isolates the dev-adapter behavior it is actually asserting.
    settings = _settings(environment, worker_auth_token=SecretStr("deployed-token"))
    assert settings.development_auth_active is False
    assert settings.development_provisioning_active is False


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_worker_auth_token_required_outside_dev(environment: Environment) -> None:
    with pytest.raises(ValidationError):
        _settings(environment)


@pytest.mark.parametrize("environment", [Environment.staging, Environment.production])
def test_worker_auth_token_present_outside_dev_succeeds(
    environment: Environment,
) -> None:
    settings = _settings(environment, worker_auth_token=SecretStr("deployed-token"))
    assert settings.worker_auth_token is not None


@pytest.mark.parametrize("environment", [Environment.development, Environment.test])
def test_worker_auth_token_optional_in_dev_and_test(
    environment: Environment,
) -> None:
    settings = _settings(environment)
    assert settings.worker_auth_token is None


def test_worker_auth_validation_error_excludes_token_value() -> None:
    # The missing-token failure must not echo any token material (there is none
    # to echo, but the message is asserted to stay generic regardless).
    with pytest.raises(ValidationError) as exc_info:
        _settings(Environment.production, worker_auth_token=None)
    assert "worker_auth_token must be configured" in str(exc_info.value)


async def test_tenant_header_is_rejected_in_production(
    app_client: Callable[..., Any],
) -> None:
    # A development header must not authenticate a tenant in production.
    async with app_client(Environment.production) as client:
        response = await client.get(
            f"/api/v1/organizations/{uuid4()}", headers=tenant_headers(uuid4())
        )
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "tenant_authentication_not_configured"


async def test_provisioning_is_rejected_in_production(
    app_client: Callable[..., Any],
) -> None:
    async with app_client(Environment.production) as client:
        response = await client.post("/api/v1/organizations", json={"name": "Acme"})
    assert response.status_code == 501
    assert (
        response.json()["error"]["code"] == "organization_provisioning_not_configured"
    )


async def test_provisioning_available_in_development(
    app_client: Callable[..., Any],
) -> None:
    async with app_client(Environment.development) as client:
        response = await client.post("/api/v1/organizations", json={"name": "Acme"})
    assert response.status_code == 201
