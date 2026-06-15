from app.constants.enums import Market, MarketStatus
from app.schemas.base import CamelModel


class StockResponse(CamelModel):
    """api-spec §2 Stock — 종목 기본 메타."""

    ticker: str
    name: str
    market: Market
    exchange: str


class QuoteResponse(CamelModel):
    """api-spec §2 Quote — 현재가/등락/당일 OHLCV."""

    ticker: str
    price: float
    change: float
    change_percent: float
    open: float
    high: float
    low: float
    volume: int
    is_delayed: bool
    market: Market


class StockSnapshotResponse(CamelModel):
    """api-spec §2 StockSnapshot — 홈 피드용 시세 스냅샷."""

    stock: StockResponse
    price: float
    change: float
    change_percent: float
    volume: int
    sparkline: list[float]


class MarketStatusResponse(CamelModel):
    """api-spec §2 — 시장별 장 상태(서버 UTC 기준 판정)."""

    market: Market
    status: MarketStatus
