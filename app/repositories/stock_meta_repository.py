from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market
from app.models.stock_meta_model import StockMeta


async def get_by_ticker(db: AsyncSession, ticker: str) -> StockMeta | None:
    statement = select(StockMeta).where(StockMeta.ticker == ticker)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def get_by_tickers(db: AsyncSession, tickers: list[str]) -> dict[str, StockMeta]:
    if not tickers:
        return {}
    statement = select(StockMeta).where(StockMeta.ticker.in_(tickers))
    result = await db.execute(statement)
    return {meta.ticker: meta for meta in result.scalars().all()}


async def search(
    db: AsyncSession,
    term: str,
    market: Market | None,
    offset: int,
    limit: int,
) -> tuple[list[StockMeta], int]:
    """name/ticker 부분일치 검색. term은 호출부에서 정규화(소문자·trim)된 비어있지 않은 값."""
    pattern = f"%{term}%"
    condition = or_(
        func.lower(StockMeta.name).like(pattern),
        func.lower(StockMeta.ticker).like(pattern),
    )
    base = select(StockMeta).where(condition)
    if market is not None:
        base = base.where(StockMeta.market == market.value)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    page = base.order_by(StockMeta.ticker).offset(offset).limit(limit)
    rows = list((await db.execute(page)).scalars().all())
    return rows, total


async def replace_all(db: AsyncSession, metas: list[StockMeta]) -> int:
    """일배치 전량 갱신 — 기존 행 삭제 후 재삽입(단일 트랜잭션)."""
    await db.execute(delete(StockMeta))
    db.add_all(metas)
    await db.commit()
    return len(metas)
