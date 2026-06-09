from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_model import User


async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
    statement = select(User).where(User.id == user_id)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


def add(db: AsyncSession, user: User) -> None:
    db.add(user)
