from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_account_model import PaperAccount
from app.models.paper_trade_model import PaperTrade


async def list_trades(
    db: AsyncSession,
    user_id: int,
    offset: int,
    limit: int,
) -> list[PaperTrade]:
    statement = (
        select(PaperTrade)
        .where(PaperTrade.user_id == user_id)
        .order_by(PaperTrade.timestamp.desc(), PaperTrade.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(statement)
    return list(result.scalars().all())


async def count_trades(db: AsyncSession, user_id: int) -> int:
    statement = select(func.count()).select_from(PaperTrade).where(PaperTrade.user_id == user_id)
    result = await db.execute(statement)
    return result.scalar_one()


async def list_all_trades_asc(db: AsyncSession, user_id: int) -> list[PaperTrade]:
    """보유현황 집계용 — 체결 순서(오름차순)로 전량 조회."""
    statement = (
        select(PaperTrade)
        .where(PaperTrade.user_id == user_id)
        .order_by(PaperTrade.timestamp, PaperTrade.id)
    )
    result = await db.execute(statement)
    return list(result.scalars().all())


def add_trade(db: AsyncSession, trade: PaperTrade) -> None:
    db.add(trade)


async def get_account(db: AsyncSession, user_id: int) -> PaperAccount | None:
    statement = select(PaperAccount).where(PaperAccount.user_id == user_id)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


def add_account(db: AsyncSession, account: PaperAccount) -> None:
    db.add(account)
