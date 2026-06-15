"""FinanceDataReader 기반 시세·종목 소싱 (feature-spec §3).

fdr 호출은 블로킹이므로 이 모듈의 함수는 모두 동기(`def`)이며, 서비스 레이어에서
`run_in_threadpool`로 감싸 async 경로를 막지 않는다(fastapi-code-rules: async route 내 블로킹 금지).
결과는 in-memory TTL 캐시로 평탄화한다.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import FinanceDataReader as fdr  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from app.constants.enums import Market
from app.constants.market import LISTING_CACHE_TTL_SECONDS, QUOTE_CACHE_TTL_SECONDS
from app.data.cache import TTLCache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StockMeta:
    """종목 기본 메타(내부 표현). API 노출은 StockResponse로 매핑."""

    ticker: str
    name: str
    market: Market
    exchange: str


_ohlcv_cache: TTLCache[tuple[str, int], pd.DataFrame] = TTLCache(QUOTE_CACHE_TTL_SECONDS)
_listing_cache: TTLCache[str, dict[str, StockMeta]] = TTLCache(LISTING_CACHE_TTL_SECONDS)

_LISTING_CACHE_KEY = "all"


def get_ohlcv(ticker: str, lookback_days: int) -> pd.DataFrame:
    """일봉 OHLCV 조회. 결과 없으면 빈 DataFrame."""
    cache_key = (ticker, lookback_days)
    cached = _ohlcv_cache.get(cache_key)

    if cached is not None:
        return cached

    start = date.today() - timedelta(days=lookback_days)
    try:
        df = fdr.DataReader(ticker, start.isoformat())
    except Exception:
        # 외부 소스 실패/타임아웃 기록(§6). 빈 프레임 반환 → 호출부는 데이터 없음으로 처리.
        logger.warning("fdr DataReader 실패 ticker=%s", ticker, exc_info=True)
        return pd.DataFrame()

    _ohlcv_cache.set(cache_key, df)
    return df


def get_listing_index() -> dict[str, StockMeta]:
    """ticker -> StockMeta 인덱스(KR KRX + US NASDAQ/NYSE). 일 1회 갱신 캐시."""
    cached = _listing_cache.get(_LISTING_CACHE_KEY)

    if cached is not None:
        return cached

    index = _load_listing_index()
    _listing_cache.set(_LISTING_CACHE_KEY, index)

    return index


def _load_listing_index() -> dict[str, StockMeta]:
    index: dict[str, StockMeta] = {}

    kr = fdr.StockListing("KRX")
    for row in kr.itertuples(index=False):
        code = getattr(row, "Code", None)
        if not code:
            continue
        exchange = str(getattr(row, "Market", "") or "")
        index[str(code)] = StockMeta(
            ticker=str(code),
            name=str(getattr(row, "Name", "") or ""),
            market=Market.KR,
            exchange=exchange,
        )

    for exchange in ("NASDAQ", "NYSE"):
        us = fdr.StockListing(exchange)
        for row in us.itertuples(index=False):
            symbol = getattr(row, "Symbol", None)
            if not symbol:
                continue
            index[str(symbol)] = StockMeta(
                ticker=str(symbol),
                name=str(getattr(row, "Name", "") or ""),
                market=Market.US,
                exchange=exchange,
            )

    return index
