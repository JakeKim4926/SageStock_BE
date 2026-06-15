from enum import StrEnum

# api-spec §0 동결 enum. 와이어 값 = 클라 Kotlin enum 이름(SCREAMING_SNAKE).
# 기존 값 rename/삭제 금지, 추가만 허용.


class Market(StrEnum):
    KR = "KR"
    US = "US"


class MarketStatus(StrEnum):
    OPEN = "OPEN"
    PRE_MARKET = "PRE_MARKET"
    AFTER_MARKET = "AFTER_MARKET"
    CLOSED = "CLOSED"


class SignalType(StrEnum):
    GOLDEN_CROSS = "GOLDEN_CROSS"
    DEAD_CROSS = "DEAD_CROSS"
    RSI_OVERSOLD = "RSI_OVERSOLD"
    RSI_OVERBOUGHT = "RSI_OVERBOUGHT"
    BOLLINGER_BREAKOUT = "BOLLINGER_BREAKOUT"
    BULLISH_DIVERGENCE = "BULLISH_DIVERGENCE"
    BEARISH_DIVERGENCE = "BEARISH_DIVERGENCE"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PredictionStatus(StrEnum):
    READY = "READY"
    PREPARING = "PREPARING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNAVAILABLE = "UNAVAILABLE"


class CrossType(StrEnum):
    GOLDEN = "GOLDEN"
    DEAD = "DEAD"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
