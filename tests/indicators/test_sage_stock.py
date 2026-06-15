import pandas as pd
import pytest

from app.indicators.sage_stock import SageStock
from tests.conftest import make_ohlcv


def test_init_requires_close_column() -> None:
    with pytest.raises(ValueError):
        SageStock(pd.DataFrame({"Open": [1.0, 2.0]}))


def test_chart_emas_added_non_destructively() -> None:
    out = SageStock(make_ohlcv(200)).Make_Chart_Emas().Get_DataFrame()

    for column in ("EMA5", "EMA20", "EMA60", "EMA120"):
        assert column in out.columns

    # 충분한 이력이면 최근 EMA120은 NaN이 아니다.
    assert pd.notna(out["EMA120"].iloc[-1])


def test_full_chart_chain_produces_all_series() -> None:
    engine = (
        SageStock(make_ohlcv(200))
        .Make_RSI()
        .Make_Bollinger_Bands()
        .Make_Stochastic()
        .Make_Disparity_EMA()
        .Make_Chart_Emas()
    )
    out = engine.Get_DataFrame()

    for column in (
        "RSI",
        "BB_Upper",
        "BB_MA20",
        "BB_Lower",
        "Stoch_K",
        "Stoch_D",
        "Disparity_EMA20",
    ):
        assert column in out.columns
