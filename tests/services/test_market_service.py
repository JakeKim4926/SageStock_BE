from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market, MarketStatus
from app.data import market_source
from app.models.watchlist_model import Watchlist
from app.services import market_service
from tests.conftest import make_ohlcv

_UTC = ZoneInfo("UTC")
_INDEX = {
    "005930": market_source.StockMeta("005930", "삼성전자", Market.KR, "KOSPI"),
    "AAPL": market_source.StockMeta("AAPL", "Apple Inc.", Market.US, "NASDAQ"),
}


def test_kr_open_during_session() -> None:
    now = datetime(2026, 6, 10, 2, 0, tzinfo=_UTC)  # 11:00 KST (Wed)
    assert market_service.resolve_market_status(Market.KR, now) == MarketStatus.OPEN


def test_kr_closed_after_session() -> None:
    now = datetime(2026, 6, 10, 8, 0, tzinfo=_UTC)  # 17:00 KST
    assert market_service.resolve_market_status(Market.KR, now) == MarketStatus.CLOSED


def test_weekend_closed() -> None:
    now = datetime(2026, 6, 13, 2, 0, tzinfo=_UTC)  # Saturday
    assert market_service.resolve_market_status(Market.KR, now) == MarketStatus.CLOSED


def test_us_open_during_session() -> None:
    now = datetime(2026, 6, 10, 14, 0, tzinfo=_UTC)  # 10:00 EDT
    assert market_service.resolve_market_status(Market.US, now) == MarketStatus.OPEN


def test_us_pre_market() -> None:
    now = datetime(2026, 6, 10, 11, 0, tzinfo=_UTC)  # 07:00 EDT
    assert market_service.resolve_market_status(Market.US, now) == MarketStatus.PRE_MARKET


def test_us_after_market() -> None:
    now = datetime(2026, 6, 10, 21, 0, tzinfo=_UTC)  # 17:00 EDT
    assert market_service.resolve_market_status(Market.US, now) == MarketStatus.AFTER_MARKET


def test_get_market_statuses_covers_all_markets() -> None:
    statuses = market_service.get_market_statuses()
    assert {status.market for status in statuses} == {Market.KR, Market.US}


@pytest.mark.asyncio
async def test_snapshots_use_watchlist_universe(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_listing_index", lambda: _INDEX)
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))
    session.add_all([Watchlist(user_id=1, ticker="005930"), Watchlist(user_id=1, ticker="AAPL")])
    await session.commit()

    snapshots = await market_service.get_snapshots(session, 1, Market.KR)

    assert all(snapshot.stock.market == Market.KR for snapshot in snapshots)
    assert {snapshot.stock.ticker for snapshot in snapshots} == {"005930"}
    assert len(snapshots[0].sparkline) == 20


@pytest.mark.asyncio
async def test_snapshots_empty_watchlist_returns_empty(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))

    assert await market_service.get_snapshots(session, 1, None) == []
