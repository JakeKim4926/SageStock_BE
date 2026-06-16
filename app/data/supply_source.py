"""KRX 수급(투자자별 순매수) 소싱 — pykrx (원본: SageStock_AI/supply.py).

종목별 반복 조회는 KRX 차단 위험이 커서, 최근 영업일 구간을 **날짜별 전종목 일괄**로 받는다.
pykrx 호출은 블로킹이라 모든 함수는 동기(`def`)이며 서비스가 run_in_threadpool로 감싼다.
결과는 당일 TTL 메모리 캐시로 평탄화(전종목 공통 → 요청마다 재수집하지 않음).

KRX 자격증명(KRX_ID/KRX_PW)이 없거나 조회 실패 시 빈 DataFrame을 반환한다 —
호출부는 수급 피처를 0으로 채워 추론을 계속한다(graceful degradation).
"""

import logging
import os
import time
from datetime import date

import pandas as pd  # type: ignore[import-untyped]

from app.constants.market import LISTING_CACHE_TTL_SECONDS
from app.core.config import settings
from app.data.cache import TTLCache

# pykrx는 import 시점에 os.environ의 KRX_ID/KRX_PW로 로그인한다. 백엔드는 .env를
# pydantic-settings로만 읽어 os.environ에 반영하지 않으므로, pykrx import 전에 주입한다.
# 이미 환경에 있으면(예: Render 대시보드 env) 그대로 둔다.
if settings.KRX_ID and settings.KRX_PW:
    os.environ.setdefault("KRX_ID", settings.KRX_ID)
    os.environ.setdefault("KRX_PW", settings.KRX_PW)

from pykrx import stock  # type: ignore[import-untyped]  # noqa: E402

logger = logging.getLogger(__name__)

# 컬럼 접두사 -> pykrx 투자자 구분값.
_INVESTORS = {"Frgn": "외국인", "Inst": "기관합계"}
_NET_COL = "순매수거래대금"
_FETCH_DELAY_SECONDS = 0.6  # 호출 간 딜레이 — KRX 차단 방어.
_DEFAULT_MARKET = "KOSDAQ"  # 모델 유니버스(kosdaq_surge).

# 당일 TTL 캐시. key=(market, lookback_bdays) -> long DataFrame(Code, Date, Frgn, Inst).
_supply_cache: TTLCache[tuple[str, int], pd.DataFrame] = TTLCache(LISTING_CACHE_TTL_SECONDS)


def _fetch_day_all(trade_date: str, market: str) -> pd.DataFrame:
    """하루치 전종목 순매수거래대금(투자자별). 휴장일/빈 응답이면 빈 DataFrame."""
    cols: dict[str, pd.Series] = {}
    for prefix, investor in _INVESTORS.items():
        df = stock.get_market_net_purchases_of_equities(trade_date, trade_date, market, investor)
        time.sleep(_FETCH_DELAY_SECONDS)
        if df is not None and not df.empty:
            cols[prefix] = df[_NET_COL]

    if not cols:
        return pd.DataFrame()

    out = pd.DataFrame(cols)
    out.index = out.index.astype(str)  # 티커 6자리 문자열.
    return out


def get_recent_supply(lookback_bdays: int, market: str = _DEFAULT_MARKET) -> pd.DataFrame:
    """최근 lookback_bdays 영업일의 전종목 외국인/기관 순매수거래대금.

    반환: (Code, Date, Frgn, Inst) long DataFrame. 실패 시 빈 DataFrame.
    """
    cache_key = (market, lookback_bdays)
    cached = _supply_cache.get(cache_key)
    if cached is not None:
        return cached

    end = pd.Timestamp(date.today())
    start = end - pd.tseries.offsets.BDay(lookback_bdays)
    days = pd.bdate_range(start, end)

    frames = []
    for day in days:
        trade_date = day.strftime("%Y%m%d")
        try:
            day_df = _fetch_day_all(trade_date, market)
        except Exception:
            logger.warning("pykrx 수급 조회 실패 date=%s market=%s", trade_date, market, exc_info=True)
            continue
        if not day_df.empty:
            day_df = day_df.copy()
            day_df["Date"] = day
            frames.append(day_df)

    if not frames:
        result = pd.DataFrame(columns=["Code", "Date", *_INVESTORS])
    else:
        result = pd.concat(frames).rename_axis("Code").reset_index()
        result = result[["Code", "Date", *[c for c in _INVESTORS if c in result.columns]]]

    _supply_cache.set(cache_key, result)
    return result
