import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import error_codes
from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.models.user_model import User
from app.repositories import user_repository

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError(error_codes.UNAUTHORIZED, "인증이 필요합니다.", 401)

    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise AppError(error_codes.TOKEN_EXPIRED, "액세스 토큰이 만료되었습니다.", 401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(error_codes.UNAUTHORIZED, "유효하지 않은 토큰입니다.", 401) from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise AppError(error_codes.UNAUTHORIZED, "유효하지 않은 토큰입니다.", 401)

    user = await user_repository.get_by_id(db, int(payload["sub"]))
    if user is None:
        raise AppError(error_codes.UNAUTHORIZED, "유효하지 않은 토큰입니다.", 401)

    return user
