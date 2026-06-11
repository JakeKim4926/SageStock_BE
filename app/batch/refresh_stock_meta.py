"""stock_meta 일배치 갱신 (feature-spec §5·§7).

fdr 리스팅(KRX + NASDAQ/NYSE)을 받아 stock_meta 테이블을 전량 교체한다.
서빙과 분리된 독립 엔트리로 cron이 일 1회 실행하는 것을 전제로 한다.

    python -m app.batch.refresh_stock_meta
"""
import asyncio
import logging
import sys

from app.core.database import async_session_factory
from app.core.logging import configure_logging
from app.data import market_source
from app.data.market_source import StockMeta as StockMetaRow
from app.models.stock_meta_model import StockMeta
from app.repositories import stock_meta_repository

logger = logging.getLogger(__name__)


def _to_model(row: StockMetaRow) -> StockMeta:
    return StockMeta(
        ticker=row.ticker,
        name=row.name,
        market=row.market.value,
        exchange=row.exchange,
    )


async def _persist(rows: list[StockMeta]) -> int:
    async with async_session_factory() as session:
        return await stock_meta_repository.replace_all(session, rows)


def main() -> None:
    configure_logging()
    try:
        index = market_source.get_listing_index()
        count = asyncio.run(_persist([_to_model(row) for row in index.values()]))
    except Exception:
        logger.exception("stock_meta 갱신 실패")
        sys.exit(1)

    logger.info("stock_meta 갱신 완료 count=%d", count)


if __name__ == "__main__":
    main()
