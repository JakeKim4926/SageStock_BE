from app.constants.enums import RiskLevel, SignalType
from app.schemas.base import CamelModel


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
