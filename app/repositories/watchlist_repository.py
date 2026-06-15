from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watchlist_model import Watchlist


async def list_tickers_by_user(db: AsyncSession, user_id: int) -> list[str]:
    statement = (
        select(Watchlist.ticker)
        .where(Watchlist.user_id == user_id)
        .order_by(Watchlist.created_at, Watchlist.id)
    )
    result = await db.execute(statement)
    return list(result.scalars().all())


async def exists(db: AsyncSession, user_id: int, ticker: str) -> bool:
    statement = select(Watchlist.id).where(
        Watchlist.user_id == user_id,
        Watchlist.ticker == ticker,
    )
    result = await db.execute(statement)
    return result.first() is not None


def add(db: AsyncSession, entry: Watchlist) -> None:
    db.add(entry)


async def delete_entry(db: AsyncSession, user_id: int, ticker: str) -> None:
    statement = delete(Watchlist).where(
        Watchlist.user_id == user_id,
        Watchlist.ticker == ticker,
    )
    await db.execute(statement)
