import pandas as pd  # type: ignore[import-untyped]

from app.constants.market import CHART_SERIES_LENGTH
from app.indicators.sage_stock import SageStock


def compute_window(df: pd.DataFrame) -> pd.DataFrame:
    """엔진 체인으로 차트 지표를 계산하고 최근 구간만 반환.

    전체 이력 위에서 계산(워밍업 확보) 후 최근 CHART_SERIES_LENGTH 봉만 잘라 candles
    인덱스와 정렬한다. 지표 조회(/indicators)와 시그널 탐지(/signals)가 공유한다.
    """
    computed = (
        SageStock(df)
        .Make_RSI()
        .Make_Bollinger_Bands()
        .Make_Stochastic()
        .Make_Disparity_EMA()
        .Make_Chart_Emas()
        .Get_DataFrame()
    )
    return computed.tail(CHART_SERIES_LENGTH)
