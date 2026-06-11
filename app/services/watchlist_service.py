from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import market_source
from app.models.watchlist_model import Watchlist
from app.repositories import watchlist_repository
from app.schemas.stock_schema import StockResponse


async def get_watchlist(db: AsyncSession, user_id: int) -> list[StockResponse]:
    tickers = await watchlist_repository.list_tickers_by_user(db, user_id)
    if not tickers:
        return []

    # 종목 메타는 리스팅 인덱스에서 조인(feature-spec §4.5). 인덱스에 없는 티커는 건너뛴다.
    # (영속 stock_meta 테이블은 B4 — DEBT_LOG.)
    index = await run_in_threadpool(market_source.get_listing_index)

    results: list[StockResponse] = []
    for ticker in tickers:
        meta = index.get(ticker)
        if meta is None:
            continue
        results.append(
            StockResponse(ticker=meta.ticker, name=meta.name, market=meta.market, exchange=meta.exchange)
        )
    return results


async def add_to_watchlist(db: AsyncSession, user_id: int, ticker: str) -> None:
    """관심종목 추가(멱등). 이미 있으면 그대로 둔다 (api-spec §3)."""
    if await watchlist_repository.exists(db, user_id, ticker):
        return

    watchlist_repository.add(db, Watchlist(user_id=user_id, ticker=ticker))
    try:
        await db.commit()
    except IntegrityError:
        # 동시 추가로 유니크 충돌 — 이미 존재하므로 멱등 성공으로 간주.
        await db.rollback()


async def remove_from_watchlist(db: AsyncSession, user_id: int, ticker: str) -> None:
    """관심종목 제거(멱등). 없어도 204 (api-spec §3)."""
    await watchlist_repository.delete_entry(db, user_id, ticker)
    await db.commit()
