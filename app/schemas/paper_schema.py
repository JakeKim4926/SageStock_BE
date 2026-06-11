from pydantic import Field

from app.constants.enums import Market, TradeSide
from app.schemas.base import CamelModel
from app.schemas.stock_schema import StockResponse


class PaperTradeResponse(CamelModel):
    """api-spec §4 PaperTrade — 가상매매 체결 기록(id·timestamp 서버 부여)."""

    id: int
    ticker: str
    name: str
    market: Market
    side: TradeSide
    price: float
    quantity: int
    timestamp: int


class PaperTradeCreateRequest(CamelModel):
    """api-spec §4 POST /paper/trades 요청. 수량·가격 ≤0 은 400 (feature-spec §4.6)."""

    ticker: str
    name: str
    market: Market
    side: TradeSide
    price: float = Field(gt=0)
    quantity: int = Field(gt=0)


class HoldingResponse(CamelModel):
    """api-spec §4 Holding — 서버 집계 보유현황. 평가손익은 클라 파생 계산."""

    stock: StockResponse
    quantity: int
    avg_price: float
    current_price: float


class AccountResponse(CamelModel):
    """api-spec §4 — 예수금/시드 요약."""

    cash: float
    seed: float
