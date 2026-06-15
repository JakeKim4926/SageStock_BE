import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.batch import refresh_stock_meta
from app.constants.enums import Market
from app.data import market_source
from app.repositories import stock_meta_repository

_INDEX = {
    "005930": market_source.StockMeta("005930", "삼성전자", Market.KR, "KOSPI"),
    "AAPL": market_source.StockMeta("AAPL", "Apple Inc.", Market.US, "NASDAQ"),
}


@pytest.mark.asyncio
async def test_persist_replaces_all_rows(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    monkeypatch,
) -> None:
    # 배치가 테스트 in-memory 엔진을 쓰도록 세션 팩토리 교체.
    monkeypatch.setattr(refresh_stock_meta, "async_session_factory", session_factory)

    rows = [refresh_stock_meta._to_model(meta) for meta in _INDEX.values()]
    count = await refresh_stock_meta._persist(rows)

    assert count == 2
    metas = await stock_meta_repository.get_by_tickers(session, ["005930", "AAPL"])
    assert set(metas) == {"005930", "AAPL"}
    assert metas["005930"].name == "삼성전자"
    assert metas["005930"].market == "KR"
