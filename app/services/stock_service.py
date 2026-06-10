import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from fastapi.concurrency import run_in_threadpool

from app.constants import error_codes
from app.constants.enums import Market
from app.constants.market import (
    CHART_SERIES_LENGTH,
    INDICATOR_LOOKBACK_DAYS,
    IS_DELAYED_DEFAULT,
    MIN_VALID_BARS,
    QUOTE_LOOKBACK_DAYS,
)
from app.core.exceptions import AppError
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.indicators.sage_stock import SageStock
from app.schemas.indicator_schema import CandleResponse, IndicatorSetResponse
from app.schemas.stock_schema import QuoteResponse, StockResponse


async def search_stocks(
    query: str,
    market: Market | None,
    page: PageParams,
) -> tuple[list[StockResponse], int]:
    normalized = query.strip().lower()

    # 빈 검색어는 클라에서 차단(api-spec §2) — 방어적으로 빈 결과 반환.
    if not normalized:
        return [], 0

    index = await run_in_threadpool(market_source.get_listing_index)

    matches = [
        meta
        for meta in index.values()
        if normalized in meta.name.lower() or normalized in meta.ticker.lower()
    ]

    if market is not None:
        matches = [meta for meta in matches if meta.market == market]

    matches.sort(key=lambda meta: meta.ticker)
    total = len(matches)
    window = matches[page.offset : page.offset + page.limit]

    results = [
        StockResponse(ticker=m.ticker, name=m.name, market=m.market, exchange=m.exchange)
        for m in window
    ]
    return results, total


async def get_stock_meta(ticker: str) -> StockResponse:
    index = await run_in_threadpool(market_source.get_listing_index)
    meta = index.get(ticker)

    if meta is None:
        raise AppError(error_codes.STOCK_NOT_FOUND, f"종목을 찾을 수 없습니다: {ticker}", 404)

    return StockResponse(ticker=meta.ticker, name=meta.name, market=meta.market, exchange=meta.exchange)


async def get_quote(ticker: str) -> QuoteResponse:
    df = await run_in_threadpool(market_source.get_ohlcv, ticker, QUOTE_LOOKBACK_DAYS)

    if df.empty:
        raise AppError(error_codes.STOCK_NOT_FOUND, f"종목을 찾을 수 없습니다: {ticker}", 404)

    last = df.iloc[-1]
    prev_close = float(df.iloc[-2]["Close"]) if len(df) >= 2 else float(last["Close"])
    price = float(last["Close"])
    change = price - prev_close
    change_percent = (change / prev_close * 100) if prev_close else 0.0

    return QuoteResponse(
        ticker=ticker,
        price=price,
        change=change,
        change_percent=change_percent,
        open=float(last["Open"]),
        high=float(last["High"]),
        low=float(last["Low"]),
        volume=int(last["Volume"]),
        is_delayed=IS_DELAYED_DEFAULT,
        market=_resolve_market(ticker),
    )


async def get_indicators(ticker: str) -> IndicatorSetResponse:
    df = await run_in_threadpool(market_source.get_ohlcv, ticker, INDICATOR_LOOKBACK_DAYS)

    if df.empty:
        raise AppError(error_codes.DATA_NOT_FOUND, f"데이터가 없습니다: {ticker}", 404)

    valid_bars = int(df["Close"].notna().sum())
    if valid_bars < MIN_VALID_BARS:
        raise AppError(
            error_codes.INSUFFICIENT_DATA,
            f"지표 산출에 필요한 데이터가 부족합니다(유효 봉 {valid_bars} < {MIN_VALID_BARS}).",
            422,
        )

    return _build_indicator_set(ticker, df)


def _build_indicator_set(ticker: str, df: pd.DataFrame) -> IndicatorSetResponse:
    # 지표는 전체 이력 위에서 계산(워밍업 확보) 후 최근 구간만 반환 → candles 인덱스와 정렬.
    engine = (
        SageStock(df)
        .Make_RSI()
        .Make_Bollinger_Bands()
        .Make_Stochastic()
        .Make_Disparity_EMA()
        .Make_Chart_Emas()
    )
    computed = engine.Get_DataFrame()
    window = computed.tail(CHART_SERIES_LENGTH)

    candles = [
        CandleResponse(
            date=index.strftime("%Y-%m-%d"),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row["Volume"]),
        )
        for index, row in window.iterrows()
    ]

    rsi_series = _series_to_list(window["RSI"])
    rsi14 = rsi_series[-1] if rsi_series else 0.0

    return IndicatorSetResponse(
        ticker=ticker,
        rsi14=rsi14,
        candles=candles,
        rsi_series=rsi_series,
        ema5=_series_to_list(window["EMA5"]),
        ema20=_series_to_list(window["EMA20"]),
        ema60=_series_to_list(window["EMA60"]),
        ema120=_series_to_list(window["EMA120"]),
        bollinger_upper=_series_to_list(window["BB_Upper"]),
        bollinger_mid=_series_to_list(window["BB_MA20"]),
        bollinger_lower=_series_to_list(window["BB_Lower"]),
        disparity_series=_series_to_list(window["Disparity_EMA20"]),
        stochastic_k=_series_to_list(window["Stoch_K"]),
        stochastic_d=_series_to_list(window["Stoch_D"]),
    )


def _series_to_list(series: pd.Series) -> list[float]:
    # 와이어는 List<Double> 비널 → 워밍업 구간의 NaN/inf를 제거(앞쪽은 첫 유효값으로 채움).
    clean = series.replace([np.inf, -np.inf], np.nan).bfill().fillna(0.0)
    return [float(value) for value in clean.tolist()]


def _resolve_market(ticker: str) -> Market:
    return Market.KR if ticker.isdigit() else Market.US
