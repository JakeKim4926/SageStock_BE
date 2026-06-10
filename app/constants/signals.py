from typing import Final

from app.constants.enums import RiskLevel, SignalType

# 시그널 탐지 표준 프리셋 (feature-spec §4.3 / D6). 코드 레벨 기본값 — 조정 가능.
# 사용자 커스텀 임계값 override는 api-spec에 파라미터 추가 후 (후속 §9).

RSI_OVERSOLD: Final = 30.0
RSI_OVERBOUGHT: Final = 70.0
# 골든/데드크로스는 차트 EMA5(fast) × EMA20(slow) 교차로 판정.
GOLDEN_FAST_SPAN: Final = 5
GOLDEN_SLOW_SPAN: Final = 20
# 다이버전스 탐지 윈도우: 직전 저점/고점과의 간격이 N봉 이내일 때만 비교.
DIVERGENCE_WINDOW: Final = 20

SIGNAL_RISK_LEVELS: Final[dict[SignalType, RiskLevel]] = {
    SignalType.GOLDEN_CROSS: RiskLevel.MEDIUM,
    SignalType.DEAD_CROSS: RiskLevel.MEDIUM,
    SignalType.RSI_OVERSOLD: RiskLevel.LOW,
    SignalType.RSI_OVERBOUGHT: RiskLevel.HIGH,
    SignalType.BOLLINGER_BREAKOUT: RiskLevel.MEDIUM,
    SignalType.BULLISH_DIVERGENCE: RiskLevel.MEDIUM,
    SignalType.BEARISH_DIVERGENCE: RiskLevel.HIGH,
}

SIGNAL_DESCRIPTIONS: Final[dict[SignalType, str]] = {
    SignalType.GOLDEN_CROSS: "5일선이 20일선을 상향 돌파",
    SignalType.DEAD_CROSS: "5일선이 20일선을 하향 돌파",
    SignalType.RSI_OVERSOLD: "RSI 과매도 (30 이하)",
    SignalType.RSI_OVERBOUGHT: "RSI 과매수 (70 이상)",
    SignalType.BOLLINGER_BREAKOUT: "종가가 볼린저 밴드를 이탈",
    SignalType.BULLISH_DIVERGENCE: "강세 다이버전스 (가격 저점↓·RSI 저점↑)",
    SignalType.BEARISH_DIVERGENCE: "약세 다이버전스 (가격 고점↑·RSI 고점↓)",
}
