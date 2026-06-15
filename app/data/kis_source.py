"""한국투자증권(KIS) REST 현재가 소싱 — 국내(KR) 실시간 시세.

국내 6자리 종목의 현재가를 KIS Open API로 조회한다. 키 미설정·비KR 종목·호출
실패 시 None을 반환해 호출측이 fdr 일봉(지연 시세)으로 폴백하도록 한다
(market_source와 동일한 실패 격리 패턴).

KIS 접근 토큰은 발급이 분당 1회로 제한되므로 모듈 레벨에 캐시하고, 동시 스냅샷
조회에서 중복 발급되지 않도록 asyncio.Lock으로 보호한다.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_PATH = "/oauth2/tokenP"
_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_PRICE_TR_ID = "FHKST01010100"  # 주식현재가 시세
_MARKET_DIV_CODE = "J"  # 주식
_HTTP_TIMEOUT = 5.0
# 만료 직전 갱신 여유(초). KIS access token 수명은 통상 24h(expires_in).
_TOKEN_REFRESH_MARGIN_SECONDS = 60

_token: str | None = None
_token_expires_at: datetime | None = None
_token_lock = asyncio.Lock()


@dataclass(frozen=True)
class KisQuote:
    """KIS 현재가(실시간) — QuoteResponse/스냅샷 매핑용 내부 표현."""

    price: float
    change: float
    change_percent: float
    open: float
    high: float
    low: float
    volume: int


def _is_kr_ticker(ticker: str) -> bool:
    return ticker.isdigit() and len(ticker) == 6


def _is_configured() -> bool:
    return bool(settings.KIS_APP_KEY and settings.KIS_APP_SECRET)


def _parse_quote(output: dict[str, str]) -> KisQuote:
    """KIS inquire-price output(문자열 필드)을 KisQuote로 변환.

    prdy_vrss는 절댓값, 부호는 prdy_vrss_sign(4·5=하락)로 결정한다. 등락률은 부호
    일관성을 위해 현재가/전일종가로 재계산한다."""
    price = float(output["stck_prpr"])
    change_magnitude = abs(float(output["prdy_vrss"]))
    is_down = output.get("prdy_vrss_sign") in ("4", "5")
    change = -change_magnitude if is_down else change_magnitude
    prev_close = price - change
    change_percent = (change / prev_close * 100) if prev_close else 0.0

    return KisQuote(
        price=price,
        change=change,
        change_percent=change_percent,
        open=float(output["stck_oprc"]),
        high=float(output["stck_hgpr"]),
        low=float(output["stck_lwpr"]),
        volume=int(output["acml_vol"]),
    )


async def _get_token(client: httpx.AsyncClient) -> str:
    """캐시된 토큰 반환, 없거나 만료 임박이면 재발급. 발급은 Lock으로 직렬화."""
    global _token, _token_expires_at

    async with _token_lock:
        now = datetime.now(UTC)
        if _token is not None and _token_expires_at is not None and now < _token_expires_at:
            return _token

        response = await client.post(
            _TOKEN_PATH,
            json={
                "grant_type": "client_credentials",
                "appkey": settings.KIS_APP_KEY,
                "appsecret": settings.KIS_APP_SECRET,
            },
        )
        response.raise_for_status()
        data = response.json()

        _token = str(data["access_token"])
        expires_in = int(data.get("expires_in", 86400))
        _token_expires_at = now + timedelta(seconds=expires_in - _TOKEN_REFRESH_MARGIN_SECONDS)
        return _token


async def get_current_quote(ticker: str) -> KisQuote | None:
    """KR 종목 실시간 현재가. 미설정·비KR·호출 실패 시 None → 호출측 fdr 폴백."""
    if not _is_configured() or not _is_kr_ticker(ticker):
        return None

    try:
        async with httpx.AsyncClient(
            base_url=settings.KIS_BASE_URL, timeout=_HTTP_TIMEOUT
        ) as client:
            token = await _get_token(client)
            response = await client.get(
                _PRICE_PATH,
                params={"fid_cond_mrkt_div_code": _MARKET_DIV_CODE, "fid_input_iscd": ticker},
                headers={
                    "content-type": "application/json; charset=utf-8",
                    "authorization": f"Bearer {token}",
                    "appkey": settings.KIS_APP_KEY,
                    "appsecret": settings.KIS_APP_SECRET,
                    "tr_id": _PRICE_TR_ID,
                    "custtype": "P",
                },
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError):
        # ValueError는 본문 JSON 디코드 실패(json.JSONDecodeError) 포함.
        logger.warning("KIS 현재가 조회 실패 ticker=%s", ticker, exc_info=True)
        return None

    if body.get("rt_cd") != "0":
        logger.warning("KIS 현재가 비정상 응답 ticker=%s rt_cd=%s", ticker, body.get("rt_cd"))
        return None

    try:
        return _parse_quote(body["output"])
    except (KeyError, ValueError):
        logger.warning("KIS 현재가 파싱 실패 ticker=%s", ticker, exc_info=True)
        return None
