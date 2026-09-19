from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.user import User
from app.db.session import get_db
from app.deps import get_current_user
from app.errors import ConflictException, UnauthenticatedException

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    query = select(User).where(User.email == req.email)
    existing = (await db.execute(query)).scalar_one_or_none()
    if existing:
        raise ConflictException("An account with this email address already exists")

    new_user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        role="user",
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return UserResponse.model_validate(new_user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and obtain JWT access token",
)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    query = select(User).where(User.email == req.email)
    user = (await db.execute(query)).scalar_one_or_none()

    if not user or not verify_password(user.password_hash, req.password):
        raise UnauthenticatedException("Invalid email or password")

    if not user.is_active:
        raise UnauthenticatedException("User account is inactive")

    settings = get_settings()
    token = create_access_token(subject=str(user.id), role=user.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)
