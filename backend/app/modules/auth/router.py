"""Authentication API router."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.modules.auth.security import decode_access_token
from app.modules.auth.service import (
    AuthenticationError,
    AuthService,
    UserExistsError,
    UserNotFoundError,
)
from app.platform.dependencies import get_db_session, get_jwt_secret

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    jwt_secret: str = Depends(get_jwt_secret),
) -> AuthService:
    return AuthService(session, jwt_secret)


def _matches_current_organization(
    user_organization_id: UUID | None, claim: Any
) -> bool:
    if user_organization_id is None:
        return claim is None
    return isinstance(claim, str) and claim == str(user_organization_id)


async def _get_current_user_payload(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(_get_auth_service),
) -> dict[str, Any]:
    """Validate the JWT against the user's current persisted security state."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token, service.jwt_secret)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user = await service.get_user_by_id(user_id)
    token_version = payload.get("tv")
    if (
        user is None
        or not user.is_active
        or payload.get("role") != user.role
        or not _matches_current_organization(
            user.organization_id, payload.get("org_id")
        )
        or not isinstance(token_version, int)
        or token_version != user.token_version
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


async def _require_admin(
    payload: dict[str, Any] = Depends(_get_current_user_payload),
) -> dict[str, Any]:
    """Require a currently active administrator account with a tenant binding."""
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        UUID(str(payload["org_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=403, detail="Administrator organization is required"
        ) from exc
    return payload


def _admin_organization_id(payload: dict[str, Any]) -> UUID:
    """Return the already-validated administrator organization claim."""
    return UUID(str(payload["org_id"]))


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    request: RegisterRequest,
    admin: dict[str, Any] = Depends(_require_admin),
    service: AuthService = Depends(_get_auth_service),
) -> UserResponse:
    """Register a new user in the current administrator's organization."""
    try:
        user = await service.register(
            request, organization_id=_admin_organization_id(admin)
        )
        return UserResponse.model_validate(user)
    except UserExistsError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    """Authenticate and receive a JWT token."""
    try:
        user, token, expires_in = await service.login(request)
        return TokenResponse(
            access_token=token,
            expires_in=expires_in,
            user=UserResponse.model_validate(user),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.detail) from exc


@router.get("/me", response_model=UserResponse)
async def get_me(
    payload: dict[str, Any] = Depends(_get_current_user_payload),
    service: AuthService = Depends(_get_auth_service),
) -> UserResponse:
    """Get the currently authenticated user."""
    user = await service.get_user_by_id(UUID(str(payload["sub"])))
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return UserResponse.model_validate(user)


@router.post("/verify-token")
async def verify_token(
    payload: dict[str, Any] = Depends(_get_current_user_payload),
) -> dict[str, Any]:
    """Verify that a token is currently valid."""
    return {
        "valid": True,
        "user_id": payload["sub"],
        "email": payload["email"],
        "role": payload["role"],
        "org_id": payload.get("org_id"),
    }


@router.post("/change-password", status_code=204)
async def change_password(
    request: ChangePasswordRequest,
    payload: dict[str, Any] = Depends(_get_current_user_payload),
    service: AuthService = Depends(_get_auth_service),
) -> None:
    """Change the current user's password and revoke their current token."""
    try:
        await service.change_password(UUID(str(payload["sub"])), request)
    except AuthenticationError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc


@router.get("/users", response_model=UserListResponse)
async def list_users(
    offset: int = 0,
    limit: int = 50,
    admin: dict[str, Any] = Depends(_require_admin),
    service: AuthService = Depends(_get_auth_service),
) -> UserListResponse:
    """List users from the current administrator's organization only."""
    users, total = await service.list_users(
        _admin_organization_id(admin), offset, limit
    )
    return UserListResponse(
        users=[UserResponse.model_validate(user) for user in users], total=total
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    admin: dict[str, Any] = Depends(_require_admin),
    service: AuthService = Depends(_get_auth_service),
) -> UserResponse:
    """Get a user from the current administrator's organization."""
    user = await service.get_user_for_organization(
        user_id, _admin_organization_id(admin)
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    request: UserUpdateRequest,
    admin: dict[str, Any] = Depends(_require_admin),
    service: AuthService = Depends(_get_auth_service),
) -> UserResponse:
    """Update a user from the current administrator's organization."""
    try:
        user = await service.update_user(
            user_id,
            request,
            organization_id=_admin_organization_id(admin),
        )
        return UserResponse.model_validate(user)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    admin: dict[str, Any] = Depends(_require_admin),
    service: AuthService = Depends(_get_auth_service),
) -> None:
    """Delete a user from the current administrator's organization."""
    try:
        await service.delete_user(
            user_id, organization_id=_admin_organization_id(admin)
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
