from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import error_codes
from app.constants.enums import Market
from app.core.exceptions import AppError
from app.dependencies.pagination_dependency import PageParams
from app.models.stock_meta_model import StockMeta
from app.repositories import stock_meta_repository
from app.schemas.stock_schema import StockResponse


async def search(
    db: AsyncSession,
    query: str,
    market: Market | None,
    page: PageParams,
) -> tuple[list[StockResponse], int]:
    normalized = query.strip().lower()
    # 빈 검색어는 클라에서 차단(api-spec §2) — 방어적으로 빈 결과 반환.
    if not normalized:
        return [], 0

    rows, total = await stock_meta_repository.search(db, normalized, market, page.offset, page.limit)
    return [_to_response(row) for row in rows], total


async def get_meta(db: AsyncSession, ticker: str) -> StockResponse:
    meta = await stock_meta_repository.get_by_ticker(db, ticker)
    if meta is None:
        raise AppError(error_codes.STOCK_NOT_FOUND, f"종목을 찾을 수 없습니다: {ticker}", 404)

    return _to_response(meta)


async def resolve_many(db: AsyncSession, tickers: list[str]) -> dict[str, StockResponse]:
    """ticker -> StockResponse 메타 조인. 인덱스에 없는 티커는 결과에서 빠진다."""
    metas = await stock_meta_repository.get_by_tickers(db, tickers)
    return {ticker: _to_response(meta) for ticker, meta in metas.items()}


def _to_response(meta: StockMeta) -> StockResponse:
    return StockResponse(
        ticker=meta.ticker,
        name=meta.name,
        market=Market(meta.market),
        exchange=meta.exchange,
    )
