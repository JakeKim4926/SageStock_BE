import pandas as pd
import pytest

from app.constants.enums import Market
from app.constants.market import SEED_UNIVERSE
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.services import signal_service
from tests.conftest import make_ohlcv


@pytest.mark.asyncio
async def test_signals_feed_detects_and_sorts_desc(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))

    results, total = await signal_service.get_signals(Market.KR, PageParams(offset=0, limit=100))

    assert total > 0
    assert len(results) == min(total, 100)
    # 최신순.
    dates = [signal.date for signal in results]
    assert dates == sorted(dates, reverse=True)
    # 식별/메타 필드.
    first = results[0]
    assert first.id.startswith(first.ticker)
    assert first.candle_index >= 0


@pytest.mark.asyncio
async def test_signals_market_filter_restricts_universe(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))

    results, _ = await signal_service.get_signals(Market.US, PageParams(offset=0, limit=100))

    us_tickers = {seed[0] for seed in SEED_UNIVERSE if seed[2] == Market.US}
    assert all(signal.ticker in us_tickers for signal in results)


@pytest.mark.asyncio
async def test_signals_skip_insufficient_data(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))

    results, total = await signal_service.get_signals(None, PageParams(offset=0, limit=20))

    assert total == 0
    assert results == []


@pytest.mark.asyncio
async def test_signals_skip_empty_frame(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: pd.DataFrame())

    results, total = await signal_service.get_signals(None, PageParams(offset=0, limit=20))

    assert total == 0
    assert results == []
