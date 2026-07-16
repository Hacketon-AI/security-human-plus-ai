"""Request/response schemas for authentication."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    role: str = Field(default="operator")
    organization_id: UUID | None = None


class LoginRequest(BaseModel):
    """Login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response after successful login."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    user: "UserResponse"


class UserResponse(BaseModel):
    """Public user data (no password hash)."""

    id: UUID
    email: str
    username: str
    full_name: str | None
    role: str
    is_active: bool
    organization_id: UUID | None
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """Admin update user request."""

    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=100)
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    organization_id: UUID | None = None


class ChangePasswordRequest(BaseModel):
    """Change password request."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserListResponse(BaseModel):
    """Paginated user list."""

    users: list[UserResponse]
    total: int
