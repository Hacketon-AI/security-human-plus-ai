"""Authentication service — business logic for user management."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User, UserRole
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserUpdateRequest,
)
from app.modules.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.modules.organizations.models import Organization


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    def __init__(self, detail: str = "Authentication failed") -> None:
        self.detail = detail
        super().__init__(detail)


class UserExistsError(Exception):
    """Raised when registering a duplicate email/username."""

    def __init__(self, detail: str = "User already exists") -> None:
        self.detail = detail
        super().__init__(detail)


class UserNotFoundError(Exception):
    """Raised when a user lookup fails."""

    def __init__(self, detail: str = "User not found") -> None:
        self.detail = detail
        super().__init__(detail)


class BootstrapOrganizationNotFoundError(Exception):
    """Raised when a configured bootstrap organization does not exist."""

    def __init__(self) -> None:
        super().__init__(
            "configured bootstrap administrator organization does not exist"
        )


class AuthService:
    """Handles organization-scoped user administration and authentication."""

    def __init__(self, session: AsyncSession, jwt_secret: str) -> None:
        self.session = session
        self.jwt_secret = jwt_secret

    async def register(
        self, request: RegisterRequest, *, organization_id: UUID
    ) -> User:
        """Register a user in the administrator's organization.

        The API never trusts ``request.organization_id``: tenant membership is
        derived from the current administrator's verified identity.
        """
        existing = await self.session.execute(
            select(User).where(User.email == str(request.email))
        )
        if existing.scalar_one_or_none() is not None:
            raise UserExistsError("Email already registered")

        existing = await self.session.execute(
            select(User).where(User.username == request.username)
        )
        if existing.scalar_one_or_none() is not None:
            raise UserExistsError("Username already taken")

        valid_roles = {role.value for role in UserRole}
        role = request.role if request.role in valid_roles else UserRole.operator
        user = User(
            email=str(request.email),
            username=request.username,
            password_hash=hash_password(request.password),
            full_name=request.full_name,
            role=role,
            is_active=True,
            organization_id=organization_id,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def login(self, request: LoginRequest) -> tuple[User, str, int]:
        """Authenticate a user and return their versioned access token."""
        result = await self.session.execute(
            select(User).where(User.email == str(request.email))
        )
        user = result.scalar_one_or_none()
        if user is None or not verify_password(request.password, user.password_hash):
            raise AuthenticationError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationError("Account is disabled")

        token, expires_in = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            organization_id=str(user.organization_id)
            if user.organization_id is not None
            else None,
            token_version=user.token_version,
            secret_key=self.jwt_secret,
        )
        user.last_login_at = datetime.now(UTC)
        await self.session.flush()
        return user, token, expires_in

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Get a user by ID without applying a tenant filter."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_for_organization(
        self, user_id: UUID, organization_id: UUID
    ) -> User | None:
        """Get a user only when it belongs to the administrator's organization."""
        result = await self.session.execute(
            select(User).where(
                User.id == user_id,
                User.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_users(
        self, organization_id: UUID, offset: int = 0, limit: int = 50
    ) -> tuple[list[User], int]:
        """List users in one organization with pagination."""
        count_result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == organization_id)
        )
        total = count_result.scalar() or 0
        result = await self.session.execute(
            select(User)
            .where(User.organization_id == organization_id)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def update_user(
        self,
        user_id: UUID,
        request: UserUpdateRequest,
        *,
        organization_id: UUID,
    ) -> User:
        """Update an organization user and revoke tokens on privilege changes."""
        user = await self.get_user_for_organization(user_id, organization_id)
        if user is None:
            raise UserNotFoundError()

        update_data = request.model_dump(exclude_unset=True)
        if update_data.get("organization_id") is not None:
            raise ValueError("organization_id cannot be changed")
        update_data.pop("organization_id", None)

        session_invalidated = False
        for field, value in update_data.items():
            if value is None:
                continue
            if field == "role" and value not in {role.value for role in UserRole}:
                raise ValueError("Invalid user role")
            if field in {"role", "is_active"} and getattr(user, field) != value:
                session_invalidated = True
            setattr(user, field, value)

        if session_invalidated:
            user.token_version += 1
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def change_password(
        self, user_id: UUID, request: ChangePasswordRequest
    ) -> None:
        """Change the current user's password and revoke existing tokens."""
        user = await self.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        if not verify_password(request.current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect")

        user.password_hash = hash_password(request.new_password)
        user.token_version += 1
        await self.session.flush()

    async def delete_user(self, user_id: UUID, *, organization_id: UUID) -> None:
        """Delete a user only if it belongs to the administrator's organization."""
        user = await self.get_user_for_organization(user_id, organization_id)
        if user is None:
            raise UserNotFoundError()
        await self.session.delete(user)
        await self.session.flush()

    async def ensure_bootstrap_admin_exists(
        self,
        *,
        email: str,
        username: str,
        password: str,
        organization_id: UUID,
        full_name: str | None,
    ) -> None:
        """Create an opt-in administrator bound to an existing organization."""
        legacy_admins = await self.session.execute(
            select(User).where(
                User.role == UserRole.admin,
                User.organization_id.is_(None),
                User.is_active.is_(True),
            )
        )
        for legacy_admin in legacy_admins.scalars():
            # A global admin cannot participate in tenant-scoped control-plane
            # actions. Disable this legacy state rather than retaining a known
            # default-password path after secure bootstrap is enabled.
            legacy_admin.is_active = False
            legacy_admin.token_version += 1

        existing_bound_admin = await self.session.execute(
            select(User)
            .where(
                User.role == UserRole.admin,
                User.organization_id.is_not(None),
                User.is_active.is_(True),
            )
            .limit(1)
        )
        if existing_bound_admin.scalar_one_or_none() is not None:
            return

        organization = await self.session.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        if organization.scalar_one_or_none() is None:
            raise BootstrapOrganizationNotFoundError()

        admin = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            role=UserRole.admin,
            is_active=True,
            organization_id=organization_id,
        )
        self.session.add(admin)
        await self.session.flush()
