from dataclasses import dataclass
from typing import Final

from app.constants.enums import Market

# api-spec §2 / feature-spec §4.2 시세·지표 관련 고정값(코드 레벨). 환경 의존 값 아님.

# 차트 시리즈 반환 길이: 최근 N 거래일 (feature-spec §4.2, 기본값 조정 가능).
CHART_SERIES_LENGTH: Final = 120
# 지표 워밍업 확보용 과거 조회 일수(달력일). ema120 등 장기선이 반환 구간에서 안정화되도록 충분히 끌어온다.
INDICATOR_LOOKBACK_DAYS: Final = 500
# 차트(/indicators) 일봉 원천 조회 일수(달력일). 주/월봉 리샘플 + 장기 EMA 워밍업까지 덮도록 8년 확보.
# 월봉 EMA120(=120개월≈10년)은 여기서 일부 부족분을 감수한다(워밍업 미충족 구간은 앞쪽이 비거나 짧아짐).
CHART_LOOKBACK_DAYS: Final = 365 * 8
# 일봉 + range=max 의 반환 상한(년). 전체 일봉 페이로드 폭주를 막아 최근 5년으로 캡한다.
CHART_DAILY_MAX_YEARS: Final = 5
# 유효 봉 최소 개수. 미만이면 422 INSUFFICIENT_DATA (feature-spec §4.2).
MIN_VALID_BARS: Final = 60
# quote 계산용 단기 조회 일수(전일 종가 대비 등락 산출).
QUOTE_LOOKBACK_DAYS: Final = 10
# 차트 EMA 기간 (api-spec IndicatorSet ema5/20/60/120).
CHART_EMA_SPANS: Final = (5, 20, 60, 120)
# 스냅샷 스파크라인 포인트 수.
SPARKLINE_LENGTH: Final = 20
# 스냅샷 조회 일수(달력일). 스파크라인 + 전일 종가 확보용.
SNAPSHOT_LOOKBACK_DAYS: Final = 40

# fdr 일봉은 지연 시세 → quote.isDelayed 기본 True (feature-spec §3).
IS_DELAYED_DEFAULT: Final = True

# 시세 캐시 TTL(초). 장중 quote/snapshot 평탄화 (feature-spec §2, 기본값 조정 가능).
QUOTE_CACHE_TTL_SECONDS: Final = 60.0
# 종목 리스팅 캐시 TTL(초). 일 1회 갱신 → 하루.
LISTING_CACHE_TTL_SECONDS: Final = 60.0 * 60 * 24

# /market/status 운영시간(현지시각, feature-spec §3, 기본값 조정 가능).
# 휴장일 판정은 후속 과제(§10) — B1은 운영시간대만 판정한다.
# KR: 정규장만(프리/애프터 없음). US: 프리/정규/애프터.
@dataclass(frozen=True)
class MarketHours:
    tz: str
    open: tuple[int, int]
    close: tuple[int, int]
    pre_open: tuple[int, int] | None = None
    after_close: tuple[int, int] | None = None


MARKET_HOURS: Final[dict[Market, MarketHours]] = {
    Market.KR: MarketHours(tz="Asia/Seoul", open=(9, 0), close=(15, 30)),
    Market.US: MarketHours(
        tz="America/New_York",
        pre_open=(4, 0),
        open=(9, 30),
        close=(16, 0),
        after_close=(20, 0),
    ),
}
