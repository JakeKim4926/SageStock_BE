from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.constants.enums import Market, MarketStatus
from app.data import market_source
from app.services import market_service
from tests.conftest import make_ohlcv

_UTC = ZoneInfo("UTC")


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
async def test_snapshots_filtered_by_market(monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))

    snapshots = await market_service.get_snapshots(Market.KR)

    assert len(snapshots) >= 1
    assert all(snapshot.stock.market == Market.KR for snapshot in snapshots)
    assert len(snapshots[0].sparkline) == 20
