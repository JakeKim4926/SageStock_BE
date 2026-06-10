"""지표 시리즈 위에서 시그널을 탐지하는 순수 함수 (feature-spec §4.3, 신규 규칙).

입력은 `chart.compute_window`가 만든 윈도우 DataFrame(RSI/EMA5/EMA20/BB_Upper/BB_Lower 포함).
반환 인덱스(candle_index)는 윈도우 내 위치 = candles 배열 인덱스와 정렬된다.
/indicators 마커(cross/divergence)와 /signals 피드가 이 결과를 공유한다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from app.constants.enums import SignalType
from app.constants.signals import DIVERGENCE_WINDOW, RSI_OVERBOUGHT, RSI_OVERSOLD


@dataclass(frozen=True)
class DetectedSignal:
    type: SignalType
    candle_index: int
    date: str


def detect_signals(window: pd.DataFrame) -> list[DetectedSignal]:
    dates = [index.strftime("%Y-%m-%d") for index in window.index]
    close = window["Close"].to_numpy(dtype=float)
    high = window["High"].to_numpy(dtype=float)
    low = window["Low"].to_numpy(dtype=float)
    rsi = window["RSI"].to_numpy(dtype=float)
    ema_fast = window["EMA5"].to_numpy(dtype=float)
    ema_slow = window["EMA20"].to_numpy(dtype=float)
    upper = window["BB_Upper"].to_numpy(dtype=float)
    lower = window["BB_Lower"].to_numpy(dtype=float)

    signals: list[DetectedSignal] = []

    for i in range(1, len(window)):
        if _finite(ema_fast[i - 1], ema_slow[i - 1], ema_fast[i], ema_slow[i]):
            prev_gap = ema_fast[i - 1] - ema_slow[i - 1]
            curr_gap = ema_fast[i] - ema_slow[i]
            if prev_gap <= 0 < curr_gap:
                signals.append(DetectedSignal(SignalType.GOLDEN_CROSS, i, dates[i]))
            elif prev_gap >= 0 > curr_gap:
                signals.append(DetectedSignal(SignalType.DEAD_CROSS, i, dates[i]))

        if _finite(rsi[i - 1], rsi[i]):
            if rsi[i - 1] > RSI_OVERSOLD >= rsi[i]:
                signals.append(DetectedSignal(SignalType.RSI_OVERSOLD, i, dates[i]))
            elif rsi[i - 1] < RSI_OVERBOUGHT <= rsi[i]:
                signals.append(DetectedSignal(SignalType.RSI_OVERBOUGHT, i, dates[i]))

        if _finite(upper[i - 1], upper[i], close[i - 1], close[i]):
            if close[i - 1] <= upper[i - 1] and close[i] > upper[i]:
                signals.append(DetectedSignal(SignalType.BOLLINGER_BREAKOUT, i, dates[i]))
        if _finite(lower[i - 1], lower[i], close[i - 1], close[i]):
            if close[i - 1] >= lower[i - 1] and close[i] < lower[i]:
                signals.append(DetectedSignal(SignalType.BOLLINGER_BREAKOUT, i, dates[i]))

    signals.extend(_detect_divergences(dates, low, high, rsi))
    signals.sort(key=lambda signal: signal.candle_index)
    return signals


def _detect_divergences(
    dates: list[str],
    low: np.ndarray,
    high: np.ndarray,
    rsi: np.ndarray,
) -> list[DetectedSignal]:
    signals: list[DetectedSignal] = []

    minima = _pivots(low, is_min=True)
    for earlier, later in zip(minima, minima[1:]):
        if later - earlier > DIVERGENCE_WINDOW or not _finite(rsi[earlier], rsi[later]):
            continue
        # 가격은 더 낮은 저점, RSI는 더 높은 저점 → 강세 다이버전스.
        if low[later] < low[earlier] and rsi[later] > rsi[earlier]:
            signals.append(DetectedSignal(SignalType.BULLISH_DIVERGENCE, later, dates[later]))

    maxima = _pivots(high, is_min=False)
    for earlier, later in zip(maxima, maxima[1:]):
        if later - earlier > DIVERGENCE_WINDOW or not _finite(rsi[earlier], rsi[later]):
            continue
        # 가격은 더 높은 고점, RSI는 더 낮은 고점 → 약세 다이버전스.
        if high[later] > high[earlier] and rsi[later] < rsi[earlier]:
            signals.append(DetectedSignal(SignalType.BEARISH_DIVERGENCE, later, dates[later]))

    return signals


def _pivots(values: np.ndarray, is_min: bool) -> list[int]:
    """3봉 기준 국소 저점/고점 인덱스."""
    pivots: list[int] = []
    for j in range(1, len(values) - 1):
        if not _finite(values[j - 1], values[j], values[j + 1]):
            continue
        if is_min and values[j] < values[j - 1] and values[j] <= values[j + 1]:
            pivots.append(j)
        elif not is_min and values[j] > values[j - 1] and values[j] >= values[j + 1]:
            pivots.append(j)
    return pivots


def _finite(*values: float) -> bool:
    return all(not np.isnan(value) for value in values)
