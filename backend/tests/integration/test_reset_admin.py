from uuid import uuid4

import pytest
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import hash_password, verify_password
from app.modules.organizations.models import Organization
from app.reset_admin import AdminRecoveryError, reset_admin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def test_creates_admin_in_single_organization(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    email = f"admin-{uuid4().hex[:8]}@example.com"
    async with session_factory() as session:
        organization = Organization(name="Acme", slug="acme")
        session.add(organization)
        await session.flush()

        result = await reset_admin(session, email=email, organization_slug=None)

        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        assert result.created
        assert user.role == UserRole.admin
        assert user.organization_id == organization.id
        assert verify_password(result.password, user.password_hash)


async def test_resets_forgotten_password_and_revokes_sessions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    email = f"operator-{uuid4().hex[:8]}@example.com"
    async with session_factory() as session:
        organization = Organization(name="Acme", slug="acme")
        session.add(organization)
        await session.flush()
        user = User(
            email=email,
            username=email.split("@")[0],
            password_hash=hash_password("forgotten-password"),
            role=UserRole.operator,
            is_active=False,
            organization_id=organization.id,
        )
        session.add(user)
        await session.flush()
        version_before = user.token_version

        result = await reset_admin(session, email=email, organization_slug=None)

        assert not result.created
        assert user.role == UserRole.admin
        assert user.is_active
        assert user.token_version == version_before + 1
        assert verify_password(result.password, user.password_hash)
        assert not verify_password("forgotten-password", user.password_hash)


async def test_requires_slug_when_organization_is_ambiguous(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add_all(
            [Organization(name="A", slug="org-a"), Organization(name="B", slug="org-b")]
        )
        await session.flush()

        with pytest.raises(AdminRecoveryError, match="org-a, org-b"):
            await reset_admin(
                session,
                email=f"x-{uuid4().hex[:8]}@example.com",
                organization_slug=None,
            )


async def test_rejects_email_the_login_endpoint_would_refuse(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(AdminRecoveryError, match="invalid email"):
            await reset_admin(
                session, email="demo@company.test", organization_slug=None
            )
