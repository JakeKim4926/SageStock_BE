import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from fastapi.concurrency import run_in_threadpool

from app.constants import error_codes
from app.constants.enums import ChartRange, CrossType, Interval, Market, SignalType
from app.constants.market import (
    CHART_DAILY_MAX_YEARS,
    CHART_LOOKBACK_DAYS,
    IS_DELAYED_DEFAULT,
    MIN_VALID_BARS,
    QUOTE_LOOKBACK_DAYS,
)
from app.core.exceptions import AppError
from app.data import kis_source, market_source
from app.indicators.chart import compute_chart_window
from app.schemas.indicator_schema import CandleResponse, CrossMarkerResponse, IndicatorSetResponse
from app.schemas.stock_schema import QuoteResponse
from app.services.signal_detector import detect_signals

# range → 마지막 캔들 기준 거슬러 볼 기간. MAX 는 트리밍 없음(전체).
_RANGE_OFFSETS: dict[ChartRange, pd.DateOffset | None] = {
    ChartRange.M1: pd.DateOffset(months=1),
    ChartRange.M3: pd.DateOffset(months=3),
    ChartRange.M6: pd.DateOffset(months=6),
    ChartRange.Y1: pd.DateOffset(years=1),
    ChartRange.MAX: None,
}


async def get_quote(ticker: str) -> QuoteResponse:
    # KR 종목은 KIS 실시간 현재가 우선. 미설정·비KR·실패 시 fdr 일봉으로 폴백.
    live = await kis_source.get_current_quote(ticker)
    if live is not None:
        return QuoteResponse(
            ticker=ticker,
            price=live.price,
            change=live.change,
            change_percent=live.change_percent,
            open=live.open,
            high=live.high,
            low=live.low,
            volume=live.volume,
            is_delayed=False,
            market=_resolve_market(ticker),
        )

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


async def get_indicators(
    ticker: str,
    interval: Interval = Interval.DAILY,
    range_: ChartRange = ChartRange.M6,
) -> IndicatorSetResponse:
    # 간격/범위 무관하게 티커당 동일한 일봉 원천을 끌어와(캐시 1엔트리 공유) 간격별로 재집계한다.
    df = await run_in_threadpool(market_source.get_ohlcv, ticker, CHART_LOOKBACK_DAYS)

    if df.empty:
        raise AppError(error_codes.DATA_NOT_FOUND, f"데이터가 없습니다: {ticker}", 404)

    valid_bars = int(df["Close"].notna().sum())
    if valid_bars < MIN_VALID_BARS:
        raise AppError(
            error_codes.INSUFFICIENT_DATA,
            f"지표 산출에 필요한 데이터가 부족합니다(유효 봉 {valid_bars} < {MIN_VALID_BARS}).",
            422,
        )

    return _build_indicator_set(ticker, df, interval, range_)


def _resolve_trim_offset(interval: Interval, range_: ChartRange) -> pd.DateOffset | None:
    # 일봉 전체는 페이로드가 커서 최근 N년으로 캡한다. 주/월봉 전체는 캔들 수가 적어 그대로 둔다.
    if range_ is ChartRange.MAX and interval is Interval.DAILY:
        return pd.DateOffset(years=CHART_DAILY_MAX_YEARS)

    return _RANGE_OFFSETS[range_]


def _build_indicator_set(
    ticker: str,
    df: pd.DataFrame,
    interval: Interval,
    range_: ChartRange,
) -> IndicatorSetResponse:
    trim_offset = _resolve_trim_offset(interval, range_)
    window = compute_chart_window(df, interval, trim_offset)

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

    # cross/divergence 마커는 /signals와 같은 탐지 로직을 공유한다 (feature-spec §4.3).
    signals = detect_signals(window)
    cross_markers = [
        CrossMarkerResponse(
            index=signal.candle_index,
            type=CrossType.GOLDEN if signal.type is SignalType.GOLDEN_CROSS else CrossType.DEAD,
        )
        for signal in signals
        if signal.type in (SignalType.GOLDEN_CROSS, SignalType.DEAD_CROSS)
    ]
    divergence_markers = [
        signal.candle_index
        for signal in signals
        if signal.type in (SignalType.BULLISH_DIVERGENCE, SignalType.BEARISH_DIVERGENCE)
    ]

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
        cross_markers=cross_markers,
        divergence_markers=divergence_markers,
    )


def _series_to_list(series: pd.Series) -> list[float]:
    # 와이어는 List<Double> 비널 → 워밍업 구간의 NaN/inf를 제거(앞쪽은 첫 유효값으로 채움).
    clean = series.replace([np.inf, -np.inf], np.nan).bfill().fillna(0.0)
    return [float(value) for value in clean.tolist()]


def _resolve_market(ticker: str) -> Market:
    return Market.KR if ticker.isdigit() else Market.US
