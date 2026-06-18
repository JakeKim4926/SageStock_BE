import pandas as pd  # type: ignore[import-untyped]

from app.constants.enums import Interval
from app.constants.market import CHART_SERIES_LENGTH
from app.indicators.sage_stock import SageStock

# 일봉 → 주/월봉 리샘플 규칙. 일봉은 리샘플하지 않으므로 매핑에 없다.
_RESAMPLE_RULES: dict[Interval, str] = {
    Interval.WEEKLY: "W-FRI",  # 금요일 마감 주봉
    Interval.MONTHLY: "ME",  # 월말 기준 월봉
}

# OHLCV 집계: 시가=구간 첫값, 고가=최댓값, 저가=최솟값, 종가=마지막값, 거래량=합.
_OHLCV_AGG: dict[str, str] = {
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last",
    "Volume": "sum",
}


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """엔진 체인으로 차트 지표를 계산한 전체 DataFrame을 반환(트리밍 없음)."""
    return (
        SageStock(df)
        .Make_RSI()
        .Make_Bollinger_Bands()
        .Make_Stochastic()
        .Make_Disparity_EMA()
        .Make_Chart_Emas()
        .Get_DataFrame()
    )


def compute_window(df: pd.DataFrame) -> pd.DataFrame:
    """일봉 지표를 계산하고 최근 CHART_SERIES_LENGTH 봉만 반환(시그널 탐지 /signals 공유).

    전체 이력 위에서 계산(워밍업 확보) 후 최근 구간만 잘라 candles 인덱스와 정렬한다.
    """
    return _compute_indicators(df).tail(CHART_SERIES_LENGTH)


def resample_ohlcv(df: pd.DataFrame, interval: Interval) -> pd.DataFrame:
    """일봉 OHLCV를 요청 간격으로 집계. 일봉이면 원본을 그대로 반환."""
    rule = _RESAMPLE_RULES.get(interval)

    if rule is None:
        return df

    resampled = df.resample(rule).agg(_OHLCV_AGG)
    # 거래가 없던 주/월(전부 NaN)은 캔들로 만들지 않는다.
    return resampled.dropna(subset=["Close"])


def compute_chart_window(
    df: pd.DataFrame,
    interval: Interval,
    trim_offset: pd.DateOffset | None,
) -> pd.DataFrame:
    """요청 간격으로 리샘플 → 그 캔들 위에서 지표 재계산 → range 만큼 잘라 반환(/indicators).

    전체 리샘플 시리즈에서 지표를 계산해 워밍업을 확보한 뒤, 마지막 캔들 기준 trim_offset
    만큼만 남긴다(trim_offset 이 None 이면 전체 반환). 마지막 캔들을 기준점으로 삼아
    시세 지연/공백에 흔들리지 않게 한다.
    """
    resampled = resample_ohlcv(df, interval)
    computed = _compute_indicators(resampled)

    if trim_offset is None or computed.empty:
        return computed

    cutoff = computed.index[-1] - trim_offset
    return computed[computed.index >= cutoff]
