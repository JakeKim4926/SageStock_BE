"""예측(/predictions) 추론 고정값. SageStock_AI XGBoost 모델 인라인 추론용.

FEATURE_COLS 순서는 학습 시점(SageStockML.FEATURE_COLS, EVENTS/PROCUREMENT 토글 OFF)과
정확히 일치해야 한다 — 순서가 어긋나면 모델 입력이 깨진다.
"""

from pathlib import Path
from typing import Final

# 종목 기술지표(15) — indicators.sage_stock.SageStock.Make_All_Indicators 산출.
STOCK_FEATURES: Final = (
    "RSI",
    "Disparity_EMA20",
    "BB_PercentB",
    "BB_Bandwidth",
    "Return_1",
    "Return_5",
    "Return_10",
    "Return_20",
    "Volatility_20",
    "Volume_Ratio",
    "MACD",
    "MACD_Hist",
    "Stoch_K",
    "Stoch_D",
    "BB_Squeeze",
)
# 시장 국면(3) — KOSDAQ 지수(KQ11).
MARKET_FEATURES: Final = ("Mkt_Ret20", "Mkt_Ret60", "Mkt_Vol20")
# 수급(5) — 기관/외국인 순매수(pykrx).
SUPPLY_FEATURES: Final = (
    "Frgn_Ratio",
    "Inst_Ratio",
    "Frgn_Ratio_5d",
    "Inst_Ratio_5d",
    "Frgn_Streak",
)
# 모델 입력 전체 피처(23). 학습 순서 고정.
FEATURE_COLS: Final = STOCK_FEATURES + MARKET_FEATURES + SUPPLY_FEATURES

# 1차 모델 통과 임계(high recall). 미만이면 메타 미적용 → confidence 0.
PRIMARY_THR: Final = 0.5
# _thr.json 부재 시 폴백 메타 임계(과거 수동값).
META_THR_FALLBACK: Final = 0.89

# 모델 자산 위치(리포 커밋). 2단계 모델 + 임계 사이드카.
MODEL_DIR: Final = Path(__file__).resolve().parent.parent / "ml" / "models"
MODEL_NAME: Final = "model_kosdaq_surge"

# 수급 rolling/연속일수 계산용 최근 영업일 수.
SUPPLY_LOOKBACK_BDAYS: Final = 20

# 해석(reasons/riskFactors) 룰: (피처, 비교, 임계, 사람말). 최신행 피처값에 적용.
# op "gt"=초과, "lt"=미만. 모델이 학습한 피처를 사용자 언어로 옮긴 명시적 룰(LLM 아님).
REASON_RULES: Final = (
    ("Volume_Ratio", "gt", 2.0, "거래량 급증"),
    ("RSI", "lt", 35.0, "RSI 과매도 반등"),
    ("MACD_Hist", "gt", 0.0, "MACD 상승 전환"),
    ("BB_Squeeze", "lt", 0.2, "변동성 압축(분출 전조)"),
    ("Frgn_Streak", "gt", 2.0, "외국인 연속 순매수"),
    ("Inst_Ratio_5d", "gt", 0.0, "기관 순매수 유입"),
    ("Mkt_Ret20", "gt", 0.0, "시장 추세 우호적"),
)
RISK_RULES: Final = (
    ("Volatility_20", "gt", 5.0, "높은 변동성"),
    ("Mkt_Vol20", "gt", 2.5, "시장 변동성 확대"),
    ("Frgn_Ratio", "lt", 0.0, "외국인 순매도"),
    ("RSI", "gt", 75.0, "단기 과열(RSI 과매수)"),
)
# 노출할 reasons/riskFactors 최대 개수.
MAX_INTERPRET_ITEMS: Final = 3
