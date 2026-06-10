import pandas as pd
import pytest

from app.constants.enums import Market
from app.core.exceptions import AppError
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.services import stock_service
from tests.conftest import make_ohlcv


@pytest.mark.asyncio
async def test_get_indicators_aligns_series_with_candles(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))

    result = await stock_service.get_indicators("005930")

    assert result.ticker == "005930"
    assert len(result.candles) == 120
    assert len(result.ema120) == len(result.candles)
    assert len(result.rsi_series) == len(result.candles)
    # 와이어는 비널 List<Double> → NaN 없이 전부 유한값.
    assert all(value == value for value in result.ema120)
    # B2: cross/divergence 마커가 채워지며, 인덱스는 candles 범위 안.
    assert all(0 <= marker.index < len(result.candles) for marker in result.cross_markers)
    assert all(0 <= index < len(result.candles) for index in result.divergence_markers)


@pytest.mark.asyncio
async def test_get_indicators_insufficient_data(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))

    with pytest.raises(AppError) as exc_info:
        await stock_service.get_indicators("005930")

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_get_indicators_not_found(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: pd.DataFrame())

    with pytest.raises(AppError) as exc_info:
        await stock_service.get_indicators("000000")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_quote_computes_change(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(10))

    quote = await stock_service.get_quote("005930")

    assert quote.ticker == "005930"
    assert quote.market == Market.KR
    assert quote.is_delayed is True


@pytest.mark.asyncio
async def test_get_quote_not_found(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: pd.DataFrame())

    with pytest.raises(AppError) as exc_info:
        await stock_service.get_quote("ZZZ")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_search_filters_by_query_and_paginates(monkeypatch) -> None:
    index = {
        "005930": market_source.StockMeta("005930", "삼성전자", Market.KR, "KOSPI"),
        "AAPL": market_source.StockMeta("AAPL", "Apple Inc.", Market.US, "NASDAQ"),
    }
    monkeypatch.setattr(market_source, "get_listing_index", lambda: index)

    results, total = await stock_service.search_stocks("apple", None, PageParams(offset=0, limit=20))

    assert total == 1
    assert results[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty() -> None:
    results, total = await stock_service.search_stocks("   ", None, PageParams(offset=0, limit=20))

    assert results == []
    assert total == 0


@pytest.mark.asyncio
async def test_get_stock_meta_not_found(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_listing_index", lambda: {})

    with pytest.raises(AppError) as exc_info:
        await stock_service.get_stock_meta("XXXX")

    assert exc_info.value.status_code == 404
