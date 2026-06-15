import asyncio

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market
from app.constants.market import INDICATOR_LOOKBACK_DAYS, MIN_VALID_BARS
from app.constants.signals import SIGNAL_DESCRIPTIONS, SIGNAL_RISK_LEVELS
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.indicators.chart import compute_window
from app.schemas.signal_schema import SignalResponse
from app.schemas.stock_schema import StockResponse
from app.services import watchlist_service
from app.services.signal_detector import DetectedSignal, detect_signals


async def get_signals(
    db: AsyncSession,
    user_id: int,
    market: Market | None,
    page: PageParams,
) -> tuple[list[SignalResponse], int]:
    # 유니버스 = 로그인 사용자 관심종목 (피드는 watchlist 기반). 비면 빈 피드.
    universe = await watchlist_service.get_watchlist(db, user_id)
    if market is not None:
        universe = [stock for stock in universe if stock.market == market]

    detected = await asyncio.gather(*[_detect_for_stock(stock) for stock in universe])
    signals = [signal for group in detected for signal in group]

    # 최신순 정렬. 같은 날짜는 삽입 순서(유니버스·캔들 순서) 유지.
    signals.sort(key=lambda signal: signal.date, reverse=True)

    total = len(signals)
    window = signals[page.offset : page.offset + page.limit]
    return window, total


async def _detect_for_stock(stock: StockResponse) -> list[SignalResponse]:
    df = await run_in_threadpool(market_source.get_ohlcv, stock.ticker, INDICATOR_LOOKBACK_DAYS)

    # 데이터 없음/부족한 종목은 피드에서 건너뛴다(전체 피드를 깨뜨리지 않음).
    if df.empty or int(df["Close"].notna().sum()) < MIN_VALID_BARS:
        return []

    indicator_window = compute_window(df)
    return [_to_response(stock.ticker, stock.name, signal) for signal in detect_signals(indicator_window)]


def _to_response(ticker: str, stock_name: str, signal: DetectedSignal) -> SignalResponse:
    return SignalResponse(
        id=f"{ticker}-{signal.date}-{signal.type.value}",
        ticker=ticker,
        stock_name=stock_name,
        type=signal.type,
        date=signal.date,
        description=SIGNAL_DESCRIPTIONS[signal.type],
        risk_level=SIGNAL_RISK_LEVELS[signal.type],
        candle_index=signal.candle_index,
    )
