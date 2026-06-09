from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_ALGORITHM: Final = "HS256"
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_TYPE: Final = "access"
REFRESH_TOKEN_TYPE: Final = "refresh"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(password, hashed_password)


def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def create_access_token(user_id: int) -> str:
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(str(user_id), ACCESS_TOKEN_TYPE, expires_delta)


def create_refresh_token(user_id: int) -> str:
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(str(user_id), REFRESH_TOKEN_TYPE, expires_delta)


def decode_token(token: str) -> dict[str, Any]:
    """토큰 검증·디코드. 만료는 jwt.ExpiredSignatureError, 그 외 무효는
    jwt.InvalidTokenError로 전파 — 호출측(인증 의존성)이 에러코드로 매핑."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
