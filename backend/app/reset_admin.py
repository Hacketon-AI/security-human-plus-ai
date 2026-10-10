"""Create an administrator or reset a forgotten administrator password.

Run where the API runs (shell access to the deployment is the trust anchor):

    python -m app.reset_admin --email you@example.com [--organization-slug acme]

A random password is generated and printed once; sign in and change it under
Settings → Account. Existing sessions of that user are revoked.
"""

import argparse
import asyncio
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import hash_password
from app.modules.organizations.models import Organization
from app.platform.database import create_engine, create_session_factory


class AdminRecoveryError(Exception):
    """The administrator cannot be created or reset as requested."""


@dataclass(frozen=True)
class AdminRecoveryResult:
    email: str
    password: str
    created: bool


async def _resolve_organization(
    session: AsyncSession, organization_slug: str | None
) -> Organization:
    query = select(Organization).order_by(Organization.slug)
    if organization_slug is not None:
        query = query.where(Organization.slug == organization_slug)
    organizations = list((await session.execute(query)).scalars())
    if len(organizations) == 1:
        return organizations[0]
    if not organizations:
        raise AdminRecoveryError(
            f"organization '{organization_slug}' not found"
            if organization_slug
            else "no organization exists; create one before the administrator"
        )
    slugs = ", ".join(organization.slug for organization in organizations)
    raise AdminRecoveryError(f"choose --organization-slug from: {slugs}")


async def reset_admin(
    session: AsyncSession, *, email: str, organization_slug: str | None
) -> AdminRecoveryResult:
    """Grant admin with a fresh password to ``email``, creating it if needed."""
    password = secrets.token_urlsafe(12)
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is not None:
        user.password_hash = hash_password(password)
        user.role = UserRole.admin
        user.is_active = True
        user.token_version += 1
        if user.organization_id is None:
            organization = await _resolve_organization(session, organization_slug)
            user.organization_id = organization.id
        await session.flush()
        return AdminRecoveryResult(email=email, password=password, created=False)

    organization = await _resolve_organization(session, organization_slug)
    username = email.split("@", 1)[0]
    taken = (
        await session.execute(select(User.id).where(User.username == username))
    ).first()
    if taken is not None:
        raise AdminRecoveryError(f"username '{username}' is already taken")

    session.add(
        User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            role=UserRole.admin,
            is_active=True,
            organization_id=organization.id,
        )
    )
    await session.flush()
    return AdminRecoveryResult(email=email, password=password, created=True)


async def _main(email: str, organization_slug: str | None) -> None:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            result = await reset_admin(
                session, email=email, organization_slug=organization_slug
            )
            await session.commit()
    finally:
        await engine.dispose()

    action = "Created" if result.created else "Reset"
    # The one-time password goes to the operator's terminal only; it is never
    # logged or stored in plaintext.
    print(f"{action} administrator {result.email}")
    print(f"Temporary password: {result.password}")
    print("Sign in and change it under Settings → Account.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--organization-slug")
    args = parser.parse_args()
    try:
        asyncio.run(_main(args.email.strip(), args.organization_slug))
    except AdminRecoveryError as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main()
