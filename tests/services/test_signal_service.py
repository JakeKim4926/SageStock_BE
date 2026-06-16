import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market, SignalType
from app.data import market_source
from app.dependencies.pagination_dependency import PageParams
from app.models.watchlist_model import Watchlist
from app.services import signal_service
from app.services.signal_detector import DetectedSignal
from app.services.signal_service import _aggregate_score
from tests.conftest import make_ohlcv, seed_stock_meta

_ROWS = [
    ("005930", "삼성전자", Market.KR, "KOSPI"),
    ("000660", "SK하이닉스", Market.KR, "KOSPI"),
    ("AAPL", "Apple Inc.", Market.US, "NASDAQ"),
]


async def _seed_watchlist(session: AsyncSession, tickers: list[str]) -> None:
    await seed_stock_meta(session, _ROWS)
    for ticker in tickers:
        session.add(Watchlist(user_id=1, ticker=ticker))
    await session.commit()


@pytest.mark.asyncio
async def test_signals_feed_detects_and_sorts_desc(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    await _seed_watchlist(session, ["005930", "000660"])

    results, total = await signal_service.get_signals(
        session, 1, Market.KR, PageParams(offset=0, limit=100)
    )

    assert total > 0
    assert len(results) == min(total, 100)
    dates = [signal.date for signal in results]
    assert dates == sorted(dates, reverse=True)
    first = results[0]
    assert first.id.startswith(first.ticker)
    assert first.candle_index >= 0


@pytest.mark.asyncio
async def test_signals_market_filter_restricts_universe(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    await _seed_watchlist(session, ["005930", "AAPL"])

    results, _ = await signal_service.get_signals(
        session, 1, Market.US, PageParams(offset=0, limit=100)
    )

    assert all(signal.ticker == "AAPL" for signal in results)


@pytest.mark.asyncio
async def test_signals_skip_insufficient_data(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))
    await _seed_watchlist(session, ["005930"])

    results, total = await signal_service.get_signals(
        session, 1, None, PageParams(offset=0, limit=20)
    )

    assert total == 0
    assert results == []


@pytest.mark.asyncio
async def test_signals_skip_empty_frame(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: pd.DataFrame())
    await _seed_watchlist(session, ["005930"])

    results, total = await signal_service.get_signals(
        session, 1, None, PageParams(offset=0, limit=20)
    )

    assert total == 0
    assert results == []


@pytest.mark.asyncio
async def test_signals_empty_watchlist_returns_empty(session: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))

    results, total = await signal_service.get_signals(
        session, 1, None, PageParams(offset=0, limit=20)
    )

    assert total == 0
    assert results == []


def test_aggregate_score_directions_and_neutral() -> None:
    # window_len=100 → last_index=99. 최신봉 시그널은 감쇠 없음(decay**0=1).
    score, buy, sell = _aggregate_score(
        [
            DetectedSignal(SignalType.GOLDEN_CROSS, 99, "d"),
            DetectedSignal(SignalType.RSI_OVERBOUGHT, 99, "d"),
            DetectedSignal(SignalType.BOLLINGER_BREAKOUT, 99, "d"),  # 중립 → 제외
        ],
        100,
    )
    assert score == 1.0  # +2(golden) -1(rsi과매수) +0(bollinger)
    assert buy == [SignalType.GOLDEN_CROSS]
    assert sell == [SignalType.RSI_OVERBOUGHT]


def test_aggregate_score_time_decay() -> None:
    score, _, _ = _aggregate_score([DetectedSignal(SignalType.GOLDEN_CROSS, 89, "d")], 100)
    assert abs(score - 2 * 0.9**10) < 1e-9  # 10봉 전 → 감쇠


def test_aggregate_score_dedup_latest() -> None:
    _, buy, _ = _aggregate_score(
        [
            DetectedSignal(SignalType.RSI_OVERSOLD, 50, "d1"),
            DetectedSignal(SignalType.RSI_OVERSOLD, 98, "d2"),
        ],
        100,
    )
    assert buy == [SignalType.RSI_OVERSOLD]  # 중복 타입 1개로 dedup


@pytest.mark.asyncio
async def test_signal_ranking_sorts_desc_and_includes_all(
    session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(250))
    await _seed_watchlist(session, ["005930", "000660"])

    results, total = await signal_service.get_signal_ranking(
        session, 1, Market.KR, PageParams(offset=0, limit=100)
    )

    assert total == 2  # 관심종목 전체 포함
    scores = [item.score for item in results]
    assert scores == sorted(scores, reverse=True)  # 매수 우세가 위


@pytest.mark.asyncio
async def test_signal_ranking_includes_insufficient_as_zero(
    session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(market_source, "get_ohlcv", lambda ticker, days: make_ohlcv(30))
    await _seed_watchlist(session, ["005930"])

    results, total = await signal_service.get_signal_ranking(
        session, 1, None, PageParams(offset=0, limit=20)
    )

    assert total == 1  # 데이터 부족도 중립으로 포함
    assert results[0].score == 0.0
    assert results[0].buy_signals == []
