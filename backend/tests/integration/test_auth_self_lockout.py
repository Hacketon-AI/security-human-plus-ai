from uuid import uuid4

import pytest
from app.modules.auth.models import User, UserRole
from app.modules.auth.schemas import UserUpdateRequest
from app.modules.auth.security import hash_password
from app.modules.auth.service import AuthService, SelfLockoutError
from app.modules.organizations.models import Organization
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.parametrize(
    "change",
    [UserUpdateRequest(is_active=False), UserUpdateRequest(role="operator")],
)
async def test_admin_cannot_remove_own_admin_access(
    session_factory: async_sessionmaker[AsyncSession], change: UserUpdateRequest
) -> None:
    async with session_factory() as session:
        organization = Organization(name="Acme", slug="acme")
        session.add(organization)
        await session.flush()
        admin = User(
            email=f"admin-{uuid4().hex[:8]}@example.com",
            username=f"admin-{uuid4().hex[:8]}",
            password_hash=hash_password("not-relevant-here"),
            role=UserRole.admin,
            organization_id=organization.id,
        )
        session.add(admin)
        await session.flush()
        service = AuthService(session, jwt_secret="test")

        with pytest.raises(SelfLockoutError):
            await service.update_user(
                admin.id, change, organization_id=organization.id, actor_id=admin.id
            )
        with pytest.raises(SelfLockoutError):
            await service.delete_user(
                admin.id, organization_id=organization.id, actor_id=admin.id
            )

        # Editing one's own non-privilege fields stays allowed.
        updated = await service.update_user(
            admin.id,
            UserUpdateRequest(full_name="Renamed"),
            organization_id=organization.id,
            actor_id=admin.id,
        )
        assert updated.full_name == "Renamed"
