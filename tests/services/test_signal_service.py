import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.models.watchlist_model import Watchlist
from app.services import signal_service
from tests.conftest import make_ohlcv, seed_stock_meta

_ROWS = [
    ("005930", "삼성전자", Market.KR, "KOSPI"),
    ("000660", "SK하이닉스", Market.KR, "KOSPI"),
    ("AAPL", "Apple Inc.", Market.US, "NASDAQ"),
]


async def _seed_watchlist(session: AsyncSession, tickers: list[str]) -> None:
    await seed_stock_meta(session, _ROWS)
    for ticker in tickers:
        session.add(Watchlist(user_id=1, ticker=ticker))
    await session.commit()


@pytest.mark.asyncio
async def test_signals_feed_detects_and_sorts_desc(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    await _seed_watchlist(session, ["005930", "000660"])

    results, total = await signal_service.get_signals(
        session, 1, Market.KR, PageParams(offset=0, limit=100)
    )

    assert total > 0
    assert len(results) == min(total, 100)
    dates = [signal.date for signal in results]
    assert dates == sorted(dates, reverse=True)
    first = results[0]
    assert first.id.startswith(first.ticker)
    assert first.candle_index >= 0


@pytest.mark.asyncio
async def test_signals_market_filter_restricts_universe(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    await _seed_watchlist(session, ["005930", "AAPL"])

    results, _ = await signal_service.get_signals(
        session, 1, Market.US, PageParams(offset=0, limit=100)
    )

    assert all(signal.ticker == "AAPL" for signal in results)


@pytest.mark.asyncio
async def test_signals_skip_insufficient_data(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))
    await _seed_watchlist(session, ["005930"])

    results, total = await signal_service.get_signals(
        session, 1, None, PageParams(offset=0, limit=20)
    )

    assert total == 0
    assert results == []


@pytest.mark.asyncio
async def test_signals_skip_empty_frame(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: pd.DataFrame())
    await _seed_watchlist(session, ["005930"])

    results, total = await signal_service.get_signals(
        session, 1, None, PageParams(offset=0, limit=20)
    )

    assert total == 0
    assert results == []


@pytest.mark.asyncio
async def test_signals_empty_watchlist_returns_empty(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))

    results, total = await signal_service.get_signals(
        session, 1, None, PageParams(offset=0, limit=20)
    )

    assert total == 0
    assert results == []
