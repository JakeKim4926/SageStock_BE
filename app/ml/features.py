"""단일 종목 OHLCV(+수급) → FEATURE_COLS(23) 벡터 조립.

종목 기술지표는 indicators.sage_stock.SageStock을 재사용하고(이미 STOCK_FEATURES 전부 생성),
시장 국면(KQ11)과 수급(pykrx) 피처를 결합한다. 원본 SageStockML.get_market_features /
add_supply_features 로직을 단일 종목용으로 이식. pandas 연산은 동기(`def`)다.
"""

import logging

import FinanceDataReader as fdr  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from app.constants.market import QUOTE_CACHE_TTL_SECONDS
from app.constants.prediction import FEATURE_COLS, SUPPLY_FEATURES, SUPPLY_LOOKBACK_BDAYS
from app.data.cache import TTLCache
from app.indicators.sage_stock import SageStock

logger = logging.getLogger(__name__)

_MARKET_INDEX = "KQ11"  # KOSDAQ 종합지수.
_market_cache: TTLCache[str, pd.DataFrame] = TTLCache(QUOTE_CACHE_TTL_SECONDS)


def get_market_features() -> pd.DataFrame:
    """KOSDAQ 지수 국면 피처(Mkt_Ret20/60, Mkt_Vol20)를 날짜별로 생성(캐시).

    전종목 공통이라 요청당 1회만 받아 종목 df에 날짜 join. 실패 시 빈 DataFrame.
    """
    cached = _market_cache.get(_MARKET_INDEX)
    if cached is not None:
        return cached

    try:
        index_close = fdr.DataReader(_MARKET_INDEX)["Close"]
    except Exception:
        logger.warning("KOSDAQ 지수(KQ11) 조회 실패", exc_info=True)
        return pd.DataFrame()

    feat = pd.DataFrame(index=index_close.index)
    feat["Mkt_Ret20"] = index_close.pct_change(20) * 100
    feat["Mkt_Ret60"] = index_close.pct_change(60) * 100
    feat["Mkt_Vol20"] = index_close.pct_change().rolling(20).std() * 100

    _market_cache.set(_MARKET_INDEX, feat)
    return feat


def _pos_streak(series: pd.Series) -> pd.Series:
    """연속 순매수(양수) 일수. 양수가 끊기면 0으로 리셋(원본 _pos_streak)."""
    positive = (series > 0).astype(int)
    reset_group = (positive == 0).cumsum()
    return positive.groupby(reset_group).cumsum()


def _add_supply_features(df: pd.DataFrame, ticker: str, supply: pd.DataFrame) -> pd.DataFrame:
    """거래대금 대비 비율로 정상화한 수급 피처를 결합. 수급 없으면 0으로 채운다."""
    df = df.copy()
    df["TradingValue"] = df["Close"] * df["Volume"]

    ticker_supply = (
        supply[supply["Code"] == ticker] if not supply.empty and "Code" in supply.columns
        else pd.DataFrame()
    )
    has_frgn = "Frgn" in ticker_supply.columns
    has_inst = "Inst" in ticker_supply.columns

    if ticker_supply.empty or not (has_frgn or has_inst):
        for column in SUPPLY_FEATURES:
            df[column] = 0.0
        return df

    keep = [c for c in ("Frgn", "Inst") if c in ticker_supply.columns]
    joined = df.join(ticker_supply.set_index("Date")[keep])

    trading_value = joined["TradingValue"].replace(0, np.nan)
    frgn = joined["Frgn"] if has_frgn else 0.0
    inst = joined["Inst"] if has_inst else 0.0
    df["Frgn_Ratio"] = (frgn / trading_value).fillna(0) if has_frgn else 0.0
    df["Inst_Ratio"] = (inst / trading_value).fillna(0) if has_inst else 0.0
    df["Frgn_Ratio_5d"] = df["Frgn_Ratio"].rolling(5, min_periods=1).sum()
    df["Inst_Ratio_5d"] = df["Inst_Ratio"].rolling(5, min_periods=1).sum()
    df["Frgn_Streak"] = _pos_streak(df["Frgn_Ratio"])
    return df


def build_feature_row(
    ohlcv: pd.DataFrame,
    ticker: str,
    supply: pd.DataFrame,
    market_features: pd.DataFrame,
) -> np.ndarray | None:
    """종목 일봉 → 최신일 FEATURE_COLS 벡터. 지표/시장/수급 결손 시 None."""
    indicators = SageStock(ohlcv).Make_All_Indicators().Drop_Na().Get_DataFrame()
    if indicators.empty:
        return None

    if market_features.empty:
        return None
    df = indicators.join(market_features).iloc[-SUPPLY_LOOKBACK_BDAYS:].copy()
    df = _add_supply_features(df, ticker, supply)

    latest = df.iloc[-1][list(FEATURE_COLS)]
    if latest.isna().any():
        return None
    return latest.to_numpy(dtype=float)
