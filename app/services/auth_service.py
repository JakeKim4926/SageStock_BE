import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import error_codes
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.refresh_token_model import RefreshToken
from app.models.user_model import User
from app.repositories import refresh_token_repository, user_repository
from app.schemas.auth_schema import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
)


def _access_expires_in() -> int:
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _issue_tokens(db: AsyncSession, user: User) -> TokenResponse:
    """access + refresh 발급. refresh의 jti를 DB에 저장(D8)."""
    jti = uuid.uuid4().hex
    refresh_token = create_refresh_token(user.id, jti)
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_token_repository.add(
        db,
        RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at),
    )

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=refresh_token,
        access_expires_in=_access_expires_in(),
    )


async def signup(db: AsyncSession, request: SignupRequest) -> TokenResponse:
    existing_user = await user_repository.get_by_email(db, request.email)
    if existing_user is not None:
        raise AppError(error_codes.CONFLICT, "이미 가입된 이메일입니다.", 409)

    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        name=request.name,
    )
    user_repository.add(db, user)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(error_codes.CONFLICT, "이미 가입된 이메일입니다.", 409) from exc

    tokens = _issue_tokens(db, user)
    await db.commit()
    return tokens


async def login(db: AsyncSession, request: LoginRequest) -> TokenResponse:
    user = await user_repository.get_by_email(db, request.email)
    if user is None or not verify_password(request.password, user.password_hash):
        raise AppError(error_codes.UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다.", 401)

    tokens = _issue_tokens(db, user)
    await db.commit()
    return tokens


async def refresh(db: AsyncSession, request: RefreshRequest) -> AccessTokenResponse:
    try:
        payload = decode_token(request.refresh_token)
    except jwt.ExpiredSignatureError as exc:
        raise AppError(error_codes.TOKEN_EXPIRED, "리프레시 토큰이 만료되었습니다.", 401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(error_codes.UNAUTHORIZED, "유효하지 않은 토큰입니다.", 401) from exc

    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise AppError(error_codes.UNAUTHORIZED, "유효하지 않은 토큰입니다.", 401)

    jti = payload.get("jti")
    stored = await refresh_token_repository.get_by_jti(db, jti) if jti else None
    if stored is None or stored.revoked:
        raise AppError(error_codes.UNAUTHORIZED, "유효하지 않은 토큰입니다.", 401)

    return AccessTokenResponse(
        access_token=create_access_token(int(payload["sub"])),
        access_expires_in=_access_expires_in(),
    )


async def logout(db: AsyncSession, request: LogoutRequest) -> None:
    """refresh 토큰 무효화. 멱등 — 토큰이 무효/없어도 204."""
    try:
        payload = decode_token(request.refresh_token, verify_exp=False)
    except jwt.InvalidTokenError:
        return

    jti = payload.get("jti")
    if not jti:
        return

    stored = await refresh_token_repository.get_by_jti(db, jti)
    if stored is not None and not stored.revoked:
        stored.revoked = True
        await db.commit()
