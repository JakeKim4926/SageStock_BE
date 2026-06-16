"""XGBoost 2단계(1차→메타) 모델 인라인 추론.

모델 3파일은 리포에 커밋(app/ml/models). 첫 호출 때 모듈 레벨로 1회 로드해 캐시한다
(kis_source 토큰 캐시 패턴). XGBoost predict는 동기·CPU·ms 단위라 호출부는 threadpool로 감싼다.
"""

import json
import logging
import threading

import numpy as np  # type: ignore[import-untyped]
import xgboost as xgb  # type: ignore[import-untyped]

from app.constants.prediction import (
    META_THR_FALLBACK,
    MODEL_DIR,
    MODEL_NAME,
    PRIMARY_THR,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_models: tuple[xgb.Booster, xgb.Booster, float] | None = None


def _load() -> tuple[xgb.Booster, xgb.Booster, float]:
    """primary/meta 모델 + 메타 임계를 1회 로드(double-checked locking).

    XGBClassifier(save_model)로 저장됐지만 순수 Booster로 로드한다 — sklearn 의존을 피하고
    더 가볍게 추론한다. objective=binary:logistic이라 Booster.predict가 양성확률을 직접 낸다.
    """
    global _models
    if _models is not None:
        return _models

    with _lock:
        if _models is not None:
            return _models

        primary = xgb.Booster()
        primary.load_model(str(MODEL_DIR / f"{MODEL_NAME}.json"))
        meta = xgb.Booster()
        meta.load_model(str(MODEL_DIR / f"{MODEL_NAME}_meta.json"))

        thr_path = MODEL_DIR / f"{MODEL_NAME}_thr.json"
        meta_thr = META_THR_FALLBACK
        if thr_path.exists():
            meta_thr = float(json.loads(thr_path.read_text())["meta_thr"])

        logger.info("예측 모델 로드 완료 (meta_thr=%.3f)", meta_thr)
        _models = (primary, meta, meta_thr)

    return _models


def get_meta_threshold() -> float:
    """매수 판정 메타 임계(_thr.json). 해석/표시용."""
    return _load()[2]


def predict(features: np.ndarray) -> tuple[float, float]:
    """단일 종목 피처 벡터(FEATURE_COLS 순서) → (rise_probability, confidence).

    1차 상승확률이 PRIMARY_THR 미만이면 메타를 적용하지 않고 confidence=0.
    메타 입력은 학습과 동일하게 피처 + 1차확률을 이어붙인다(screen.py와 일치).
    """
    primary, meta, _ = _load()

    rise_probability = float(primary.predict(xgb.DMatrix(features.reshape(1, -1)))[0])
    if rise_probability < PRIMARY_THR:
        return rise_probability, 0.0

    meta_input = np.append(features, rise_probability).reshape(1, -1)
    confidence = float(meta.predict(xgb.DMatrix(meta_input))[0])
    return rise_probability, confidence
