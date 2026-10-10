"""Viewers can read tenant data but every state-changing request is refused."""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import hash_password
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

CreateOrg = Callable[..., Awaitable[dict[str, Any]]]
_PASSWORD = "correct-horse-battery"


async def _bearer(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: str,
    role: UserRole,
) -> dict[str, str]:
    email = f"{role.value}-{uuid4().hex[:8]}@example.com"
    async with session_factory() as session:
        session.add(
            User(
                email=email,
                username=email.split("@")[0],
                password_hash=hash_password(_PASSWORD),
                role=role,
                organization_id=UUID(organization_id),
            )
        )
        await session.commit()
    response = await client.post(
        "/auth/login", json={"email": email, "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize(
    ("role", "write_status"), [(UserRole.viewer, 403), (UserRole.operator, 201)]
)
async def test_only_viewers_are_read_only(
    client: AsyncClient,
    create_organization: CreateOrg,
    session_factory: async_sessionmaker[AsyncSession],
    role: UserRole,
    write_status: int,
) -> None:
    org = await create_organization()
    headers = await _bearer(client, session_factory, org["id"], role)

    read = await client.get("/api/v1/projects", headers=headers)
    write = await client.post(
        "/api/v1/projects", json={"name": f"P {role.value}"}, headers=headers
    )

    assert read.status_code == 200
    assert write.status_code == write_status, write.text
    if role is UserRole.viewer:
        assert write.json()["error"]["code"] == "read_only_role"
