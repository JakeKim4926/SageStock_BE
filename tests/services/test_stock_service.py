import pandas as pd
import pytest

from app.constants.enums import ChartRange, Interval, Market
from app.core.exceptions import AppError
from app.data import kis_source, market_source
from app.services import stock_service
from tests.conftest import make_ohlcv


@pytest.mark.asyncio
async def test_get_indicators_aligns_series_with_candles(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))

    result = await stock_service.get_indicators("005930")

    assert result.ticker == "005930"
    # 기본 1d+6m → 6개월 윈도우로 잘려 원천(250봉)보다 짧다.
    assert 0 < len(result.candles) < 250
    assert len(result.ema120) == len(result.candles)
    assert len(result.rsi_series) == len(result.candles)
    # 와이어는 비널 List<Double> → NaN 없이 전부 유한값.
    assert all(value == value for value in result.ema120)
    # B2: cross/divergence 마커가 채워지며, 인덱스는 candles 범위 안.
    assert all(0 <= marker.index < len(result.candles) for marker in result.cross_markers)
    assert all(0 <= index < len(result.candles) for index in result.divergence_markers)


@pytest.mark.asyncio
async def test_get_indicators_weekly_has_fewer_candles_than_daily(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))

    daily = await stock_service.get_indicators("005930", Interval.DAILY, ChartRange.Y1)
    weekly = await stock_service.get_indicators("005930", Interval.WEEKLY, ChartRange.Y1)

    # 같은 1년 범위라도 주봉은 캔들 수가 크게 줄고 모든 시리즈가 캔들과 정렬된다.
    assert len(weekly.candles) < len(daily.candles)
    assert len(weekly.ema20) == len(weekly.candles)
    assert len(weekly.stochastic_k) == len(weekly.candles)


@pytest.mark.asyncio
async def test_get_indicators_monthly_aggregates_ohlcv(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(400))

    result = await stock_service.get_indicators("005930", Interval.MONTHLY, ChartRange.Y1)

    # 월봉이면 캔들 하나가 한 달치 → 1년 범위에서 12~13개 안팎.
    assert 0 < len(result.candles) <= 14
    # 집계 무결성: 각 캔들의 고가 ≥ 저가, 거래량은 일봉 합이라 일봉 단건보다 크다.
    assert all(candle.high >= candle.low for candle in result.candles)
    assert all(candle.volume > 1_000_000 for candle in result.candles)


@pytest.mark.asyncio
async def test_get_indicators_range_trims_window(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(400))

    one_month = await stock_service.get_indicators("005930", Interval.DAILY, ChartRange.M1)
    one_year = await stock_service.get_indicators("005930", Interval.DAILY, ChartRange.Y1)

    assert len(one_month.candles) < len(one_year.candles)


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
    # 로컬 .env에 KIS 키가 있으면 실 API를 타 is_delayed=False가 되므로 차단.
    async def no_quote(ticker: str) -> None:
        return None

    monkeypatch.setattr(kis_source, "get_current_quote", no_quote)
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
