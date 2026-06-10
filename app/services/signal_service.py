import asyncio

from fastapi.concurrency import run_in_threadpool

from app.constants.enums import Market
from app.constants.market import INDICATOR_LOOKBACK_DAYS, MIN_VALID_BARS, SEED_UNIVERSE
from app.constants.signals import SIGNAL_DESCRIPTIONS, SIGNAL_RISK_LEVELS
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.indicators.chart import compute_window
from app.indicators.signal_detector import DetectedSignal, detect_signals
from app.schemas.signal_schema import SignalResponse


async def get_signals(
    market: Market | None,
    page: PageParams,
) -> tuple[list[SignalResponse], int]:
    # 유니버스는 B1 스냅샷과 동일한 임시 시드 (B3에서 watchlist 기반으로 교체).
    universe = [seed for seed in SEED_UNIVERSE if market is None or seed[2] == market]

    detected = await asyncio.gather(*[_detect_for_seed(seed) for seed in universe])
    signals = [signal for group in detected for signal in group]

    # 최신순 정렬. 같은 날짜는 삽입 순서(유니버스·캔들 순서) 유지.
    signals.sort(key=lambda signal: signal.date, reverse=True)

    total = len(signals)
    window = signals[page.offset : page.offset + page.limit]
    return window, total


async def _detect_for_seed(seed: tuple[str, str, Market, str]) -> list[SignalResponse]:
    ticker, name, _market, _exchange = seed
    df = await run_in_threadpool(market_source.get_ohlcv, ticker, INDICATOR_LOOKBACK_DAYS)

    # 데이터 없음/부족한 종목은 피드에서 건너뛴다(전체 피드를 깨뜨리지 않음).
    if df.empty or int(df["Close"].notna().sum()) < MIN_VALID_BARS:
        return []

    indicator_window = compute_window(df)
    return [_to_response(ticker, name, signal) for signal in detect_signals(indicator_window)]


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
