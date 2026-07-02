"""Slug uniqueness under concurrency.

The database unique constraints are the source of truth. These tests prove that
a lost race resolves to a clean 409, never a 500, and that the IntegrityError
path maps specifically to a slug conflict.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.modules.organizations.errors import OrganizationSlugConflict
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationCreate
from app.modules.organizations.service import OrganizationService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import tenant_headers


async def test_concurrent_org_creation_yields_one_success_no_500(
    client: AsyncClient,
) -> None:
    async def _create() -> int:
        response = await client.post(
            "/api/v1/organizations", json={"name": "Race", "slug": "race"}
        )
        return response.status_code

    results = await asyncio.gather(*[_create() for _ in range(6)])

    assert 500 not in results
    assert results.count(201) == 1
    assert all(status in (201, 409) for status in results)


async def test_concurrent_project_creation_yields_one_success_no_500(
    client: AsyncClient,
    create_organization: Callable[..., Awaitable[dict[str, Any]]],
) -> None:
    organization = await create_organization()
    headers = tenant_headers(organization["id"])

    async def _create() -> int:
        response = await client.post(
            "/api/v1/projects",
            json={"name": "Core", "slug": "core"},
            headers=headers,
        )
        return response.status_code

    results = await asyncio.gather(*[_create() for _ in range(6)])

    assert 500 not in results
    assert results.count(201) == 1
    assert all(status in (201, 409) for status in results)


async def test_org_slug_integrity_violation_maps_to_conflict(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Persist the first organization normally.
    async with session_factory() as session:
        service = OrganizationService(OrganizationRepository(session))
        await service.create(OrganizationCreate(name="Acme", slug="acme"))
        await session.commit()

    # Force the rare path: a pre-check that misses, so the insert hits the DB
    # unique constraint directly. It must become a 409, not a 500.
    async with session_factory() as session:
        repository = OrganizationRepository(session)
        # Simulate a pre-check that misses the concurrent insert.
        repository.slug_exists = AsyncMock(return_value=False)
        service = OrganizationService(repository)
        with pytest.raises(OrganizationSlugConflict):
            await service.create(OrganizationCreate(name="Acme Two", slug="acme"))
        await session.rollback()
