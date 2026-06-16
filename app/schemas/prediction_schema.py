from pydantic import Field

from app.constants.enums import PredictionStatus
from app.schemas.base import CamelModel
from app.schemas.stock_schema import StockResponse


class PredictionResponse(CamelModel):
    """api-spec §2 Prediction — XGBoost 추론 결과.

    status != READY이면 확률/수익/근거는 기본값(0/빈배열)이다(api-spec 허용).
    expectedReturnPercent는 1단계 미산출(모델이 분류기라 종목별 기대수익을 내지 않음).
    """

    stock: StockResponse
    status: PredictionStatus
    rise_probability: float = 0.0
    expected_return_percent: float = 0.0
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
