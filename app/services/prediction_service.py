"""예측 피드 서비스. 관심종목 유니버스에 XGBoost 2단계 모델을 적용(signal_service 골격).

전종목 공통 자원(시장 국면·수급)은 요청당 1회만 받아 공유하고, 종목별 시세 조회만
threadpool로 감싼다. 비KR·데이터 부족 종목은 status로 구분해 피드를 깨뜨리지 않는다.
"""

import asyncio

import numpy as np  # type: ignore[import-untyped]
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.enums import Market, PredictionStatus
from app.constants.market import INDICATOR_LOOKBACK_DAYS, MIN_VALID_BARS
from app.constants.prediction import (
    FEATURE_COLS,
    MAX_INTERPRET_ITEMS,
    REASON_RULES,
    RISK_RULES,
    SUPPLY_LOOKBACK_BDAYS,
)
from app.data import market_source, supply_source
from app.dependencies.pagination_dependency import PageParams
from app.ml import features, predictor
from app.schemas.prediction_schema import PredictionResponse
from app.schemas.stock_schema import StockResponse
from app.services import watchlist_service

_FEATURE_INDEX = {name: position for position, name in enumerate(FEATURE_COLS)}


async def get_predictions(
    db: AsyncSession,
    user_id: int,
    market: Market | None,
    page: PageParams,
) -> tuple[list[PredictionResponse], int]:
    # 유니버스 = 로그인 사용자 관심종목(피드는 watchlist 기반). 비면 빈 피드.
    universe = await watchlist_service.get_watchlist(db, user_id)
    if market is not None:
        universe = [stock for stock in universe if stock.market == market]

    if not universe:
        return [], 0

    # 시장 국면·수급은 전종목 공통 → 1회만 받아 공유(블로킹이라 threadpool).
    market_features = await run_in_threadpool(features.get_market_features)
    supply = await run_in_threadpool(supply_source.get_recent_supply, SUPPLY_LOOKBACK_BDAYS)

    predictions = await asyncio.gather(
        *[_predict_for_stock(stock, supply, market_features) for stock in universe]
    )

    total = len(predictions)
    window = predictions[page.offset : page.offset + page.limit]
    return window, total


async def _predict_for_stock(
    stock: StockResponse,
    supply,
    market_features,
) -> PredictionResponse:
    # 모델 유니버스는 KOSDAQ(KR). 그 외 시장은 미지원으로 표시한다.
    if stock.market is not Market.KR:
        return PredictionResponse(stock=stock, status=PredictionStatus.UNAVAILABLE)

    df = await run_in_threadpool(market_source.get_ohlcv, stock.ticker, INDICATOR_LOOKBACK_DAYS)
    if df.empty or int(df["Close"].notna().sum()) < MIN_VALID_BARS:
        return PredictionResponse(stock=stock, status=PredictionStatus.INSUFFICIENT_DATA)

    row = features.build_feature_row(df, stock.ticker, supply, market_features)
    if row is None:
        return PredictionResponse(stock=stock, status=PredictionStatus.INSUFFICIENT_DATA)

    rise_probability, confidence = predictor.predict(row)
    reasons, risk_factors = _interpret(row)
    return PredictionResponse(
        stock=stock,
        status=PredictionStatus.READY,
        rise_probability=rise_probability,
        confidence=confidence,
        reasons=reasons,
        risk_factors=risk_factors,
    )


def _interpret(row: np.ndarray) -> tuple[list[str], list[str]]:
    """최신행 피처값을 룰에 대입해 reasons/riskFactors 생성(명시적 룰, LLM 아님)."""
    return _apply_rules(row, REASON_RULES), _apply_rules(row, RISK_RULES)


def _apply_rules(
    row: np.ndarray,
    rules: tuple[tuple[str, str, float, str], ...],
) -> list[str]:
    hits: list[str] = []
    for feature, op, threshold, label in rules:
        value = row[_FEATURE_INDEX[feature]]
        if (op == "gt" and value > threshold) or (op == "lt" and value < threshold):
            hits.append(label)
        if len(hits) >= MAX_INTERPRET_ITEMS:
            break
    return hits
