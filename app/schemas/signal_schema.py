from pydantic import Field

from app.constants.enums import RiskLevel, SignalType
from app.schemas.base import CamelModel
from app.schemas.stock_schema import StockResponse


class SignalResponse(CamelModel):
    """api-spec §2 Signal — 지표 기반 탐지 시그널."""

    id: str
    ticker: str
    stock_name: str
    type: SignalType
    date: str
    description: str
    risk_level: RiskLevel
    candle_index: int = -1


class SignalScoreResponse(CamelModel):
    """관심종목 시그널 종합점수(/signals/ranking).

    score는 탐지 시그널을 매수(+)/매도(-) 가중·시간감쇠로 합산한 값.
    내림차순 정렬 시 위=매수 우세, 아래=매도 우세.
    """

    stock: StockResponse
    score: float = 0.0
    buy_signals: list[SignalType] = Field(default_factory=list)
    sell_signals: list[SignalType] = Field(default_factory=list)
