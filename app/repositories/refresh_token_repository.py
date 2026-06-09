from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token_model import RefreshToken


async def get_by_jti(db: AsyncSession, jti: str) -> RefreshToken | None:
    statement = select(RefreshToken).where(RefreshToken.jti == jti)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


def add(db: AsyncSession, token: RefreshToken) -> None:
    db.add(token)
