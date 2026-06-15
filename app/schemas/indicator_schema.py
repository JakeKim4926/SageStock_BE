from app.constants.enums import CrossType
from app.schemas.base import CamelModel


class CandleResponse(CamelModel):
    """api-spec §2 Candle — 일봉 OHLCV."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class CrossMarkerResponse(CamelModel):
    """api-spec §2 CrossMarker — 차트 위 교차 마커(candles 인덱스 기준)."""

    index: int
    type: CrossType


class IndicatorSetResponse(CamelModel):
    """api-spec §2 IndicatorSet — 차트 오버레이용 지표 시리즈.

    모든 시리즈는 candles 인덱스와 정렬한다(차트 오버레이 기준).
    cross_markers / divergence_markers 는 시그널 탐지(B2)에서 채운다 — B1은 빈 배열.
    """

    ticker: str
    rsi14: float
    candles: list[CandleResponse]
    rsi_series: list[float]
    ema5: list[float]
    ema20: list[float]
    ema60: list[float]
    ema120: list[float]
    bollinger_upper: list[float]
    bollinger_mid: list[float]
    bollinger_lower: list[float]
    disparity_series: list[float]
    stochastic_k: list[float]
    stochastic_d: list[float]
    cross_markers: list[CrossMarkerResponse] = []
    divergence_markers: list[int] = []
