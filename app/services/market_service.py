import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi.concurrency import run_in_threadpool

from app.constants.enums import Market, MarketStatus
from app.constants.market import (
    MARKET_HOURS,
    SEED_UNIVERSE,
    SNAPSHOT_LOOKBACK_DAYS,
    SPARKLINE_LENGTH,
)
from app.data import market_source
from app.schemas.stock_schema import MarketStatusResponse, StockResponse, StockSnapshotResponse


async def get_snapshots(market: Market | None) -> list[StockSnapshotResponse]:
    universe = [
        seed for seed in SEED_UNIVERSE if market is None or seed[2] == market
    ]

    snapshots = await asyncio.gather(*[_build_snapshot(seed) for seed in universe])
    return [snapshot for snapshot in snapshots if snapshot is not None]


async def _build_snapshot(
    seed: tuple[str, str, Market, str],
) -> StockSnapshotResponse | None:
    ticker, name, market, exchange = seed
    df = await run_in_threadpool(market_source.get_ohlcv, ticker, SNAPSHOT_LOOKBACK_DAYS)

    # 시드 종목이 일시적으로 조회 실패해도 전체 피드를 깨뜨리지 않는다.
    if df.empty:
        return None

    closes = [float(value) for value in df["Close"].tail(SPARKLINE_LENGTH).tolist()]
    price = float(df.iloc[-1]["Close"])
    prev_close = float(df.iloc[-2]["Close"]) if len(df) >= 2 else price
    change = price - prev_close
    change_percent = (change / prev_close * 100) if prev_close else 0.0

    return StockSnapshotResponse(
        stock=StockResponse(ticker=ticker, name=name, market=market, exchange=exchange),
        price=price,
        change=change,
        change_percent=change_percent,
        volume=int(df.iloc[-1]["Volume"]),
        sparkline=closes,
    )


def get_market_statuses() -> list[MarketStatusResponse]:
    now_utc = datetime.now(ZoneInfo("UTC"))
    return [
        MarketStatusResponse(market=market, status=resolve_market_status(market, now_utc))
        for market in Market
    ]


def resolve_market_status(market: Market, now_utc: datetime) -> MarketStatus:
    """서버 UTC 시각을 시장 현지시각으로 변환해 운영시간대만 판정(휴장일은 후속, feature-spec §3)."""
    hours = MARKET_HOURS[market]
    local = now_utc.astimezone(ZoneInfo(hours.tz))

    # 주말은 휴장. (공휴일 캘린더는 후속 과제 §10.)
    if local.weekday() >= 5:
        return MarketStatus.CLOSED

    now = local.time()
    open_time = time(*hours.open)
    close_time = time(*hours.close)

    if hours.pre_open is not None and time(*hours.pre_open) <= now < open_time:
        return MarketStatus.PRE_MARKET

    if hours.after_close is not None and close_time <= now < time(*hours.after_close):
        return MarketStatus.AFTER_MARKET

    if open_time <= now < close_time:
        return MarketStatus.OPEN

    return MarketStatus.CLOSED
