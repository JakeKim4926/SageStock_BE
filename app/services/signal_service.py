import asyncio

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market, SignalType
from app.constants.market import INDICATOR_LOOKBACK_DAYS, MIN_VALID_BARS
from app.constants.signals import (
    SCORE_DECAY,
    SIGNAL_DESCRIPTIONS,
    SIGNAL_RISK_LEVELS,
    SIGNAL_WEIGHTS,
)
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.indicators.chart import compute_window
from app.schemas.signal_schema import SignalResponse, SignalScoreResponse
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


async def get_signal_ranking(
    db: AsyncSession,
    user_id: int,
    market: Market | None,
    page: PageParams,
) -> tuple[list[SignalScoreResponse], int]:
    # 유니버스 = 관심종목. 비면 빈 랭킹(empty-state 폴백은 범위 밖).
    universe = await watchlist_service.get_watchlist(db, user_id)
    if market is not None:
        universe = [stock for stock in universe if stock.market == market]

    scored = await asyncio.gather(*[_score_for_stock(stock) for stock in universe])
    # 매수 우세(점수↑)가 위, 매도 우세(점수↓)가 아래.
    scored.sort(key=lambda item: item.score, reverse=True)

    total = len(scored)
    window = scored[page.offset : page.offset + page.limit]
    return window, total


async def _score_for_stock(stock: StockResponse) -> SignalScoreResponse:
    df = await run_in_threadpool(market_source.get_ohlcv, stock.ticker, INDICATOR_LOOKBACK_DAYS)

    # 데이터 부족 종목도 관심종목 전체 노출을 위해 중립(score=0)으로 포함.
    if df.empty or int(df["Close"].notna().sum()) < MIN_VALID_BARS:
        return SignalScoreResponse(stock=stock)

    window = compute_window(df)
    score, buy_signals, sell_signals = _aggregate_score(detect_signals(window), len(window))
    return SignalScoreResponse(
        stock=stock,
        score=score,
        buy_signals=buy_signals,
        sell_signals=sell_signals,
    )


def _aggregate_score(
    signals: list[DetectedSignal],
    window_len: int,
) -> tuple[float, list[SignalType], list[SignalType]]:
    """탐지 시그널을 매수(+)/매도(-) 가중·시간감쇠로 합산. 표시용 시그널은 최신순 dedup."""
    last_index = window_len - 1
    score = 0.0
    buy: list[SignalType] = []
    sell: list[SignalType] = []

    for signal in signals:
        weight = SIGNAL_WEIGHTS[signal.type]
        if weight == 0:
            continue
        score += weight * (SCORE_DECAY ** (last_index - signal.candle_index))
        (buy if weight > 0 else sell).append(signal.type)

    return score, _dedup_latest(buy), _dedup_latest(sell)


def _dedup_latest(signal_types: list[SignalType]) -> list[SignalType]:
    """중복 시그널 타입을 최신 등장 우선으로 제거(detect_signals는 과거→최신 순)."""
    seen: set[SignalType] = set()
    result: list[SignalType] = []
    for signal_type in reversed(signal_types):
        if signal_type not in seen:
            seen.add(signal_type)
            result.append(signal_type)
    return result
